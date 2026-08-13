#authentication and authorization 
from datetime import datetime, timedelta, timezone

import bcrypt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings
from app.db import users

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    # bcrypt silently truncates at 72 bytes, so reject longer input rather
    # than let two different passwords hash the same.
    if len(password.encode()) > 72:
        raise HTTPException(400, "Password must be at most 72 bytes.")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": user_id, "exp": expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def current_user(token: str = Depends(oauth2_scheme)) -> dict:
     credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_error
        oid = ObjectId(user_id)
    except (JWTError, InvalidId):
        raise credentials_error

    user = await users().find_one({"_id": oid})
    if user is None:
        raise credentials_error
    return user
