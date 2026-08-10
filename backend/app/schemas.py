"""Request/response models. Mongo documents are plain dicts; these only
describe what crosses the HTTP boundary."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


# Login has no request model: the endpoint takes an OAuth2PasswordRequestForm
# so the Swagger "Authorize" button works.


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime


class DocumentOut(BaseModel):
    """A stored resume or JD."""

    id: str
    kind: str  # "resume" | "jd"
    preview: str
    created_at: datetime


class MatchRequest(BaseModel):
    resume_id: str
    jd_id: str


class MatchOut(BaseModel):
    id: str
    resume_id: str
    jd_id: str
    cosine_score: float
    cross_encoder_score: float
    final_score: float
    features: dict
    explanation_text: str
    created_at: datetime


class FeedbackRequest(BaseModel):
    match_id: str
    user_rating: int = Field(ge=-1, le=1)
    corrected_score: float | None = Field(default=None, ge=0, le=1)
    comment: str = ""
