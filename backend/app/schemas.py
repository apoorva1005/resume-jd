#Request/response models. Mongo documents are plain dicts
#these only describe what crosses the HTTP boundary
#entering and leaving your FastAPI API
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime


class DocumentOut(BaseModel):

    id: str
    kind: str  # "resume" | "jd"
    preview: str
    created_at: datetime
    indexed: bool = False


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


class MetadataFilters(BaseModel):
    min_years: int | None = Field(default=None, ge=0, le=50)
    min_degree_rank: int | None = Field(default=None, ge=0, le=3)
    source: Literal["file", "text"] | None = None
    created_after: datetime | None = None
    has_skills_section: bool | None = None
    must_contain: str | None = Field(default=None, max_length=200)


class SearchRequest(BaseModel):
    query_id: str | None = None
    query_text: str | None = Field(default=None, max_length=20000)
    k: int = Field(default=5, ge=1, le=50)
    filters: MetadataFilters = Field(default_factory=MetadataFilters)


class SearchHit(BaseModel):
    id: str
    kind: str
    similarity: float  # cosine similarity in [0, 1]
    preview: str
    created_at: datetime | None = None
    years_experience: int | None = None
    degree_rank: int | None = None
    source: str | None = None
    filename: str | None = None


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    count: int
    filters_applied: list[str]
    query_kind: str
    searched_kind: str


class VectorStatsResponse(BaseModel):
    resume_vectors: int
    jd_vectors: int
    mode: str
