
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.errors import DuplicateKeyError

from app.auth import (
    create_access_token,
    current_user,
    hash_password,
    verify_password,
)
from app.db import users
from app.schemas import SignupRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(body: SignupRequest):
    doc = {
        "email": body.email.lower(),
        "hashed_password": hash_password(body.password),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await users().insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "That email is already registered.")
    return TokenResponse(access_token=create_access_token(str(result.inserted_id)))


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    # OAuth2PasswordRequestForm calls the field "username"; we put the email
    # in it so the standard Swagger "Authorize" button works.
    user = await users().find_one({"email": form.username.lower()})
    if user is None or not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(401, "Incorrect email or password.")
    return TokenResponse(access_token=create_access_token(str(user["_id"])))


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)):
    return UserOut(
        id=str(user["_id"]),
        email=user["email"],
        created_at=user["created_at"],
    )
