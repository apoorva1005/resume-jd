#Request/response models. Mongo documents are plain dicts
#these only describe what crosses the HTTP boundary

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
    # False when the vector isn't in Chroma -- either the upload couldn't reach
    # it, or the document predates the vector index. Still in Mongo and still
    # matchable; it just won't turn up in vector search until
    # scripts/reindex_chroma.py runs.
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


class FeedbackRequest(BaseModel):
    match_id: str
    user_rating: int = Field(ge=-1, le=1)
    corrected_score: float | None = Field(default=None, ge=0, le=1)
    comment: str = ""


# --- Vector search -------------------------------------------------------
# These describe Chroma queries. `MetadataFilters` maps onto a Chroma `where`
# clause (plus `where_document` for must_contain); see
# services/vector_search.py for the translation.


class MetadataFilters(BaseModel):
    """Pre-filters applied before the vector search, not after it."""

    min_years: int | None = Field(default=None, ge=0, le=50)
    # Matches DEGREE_RANK in features.py: 1 bachelors, 2 masters, 3 doctorate.
    min_degree_rank: int | None = Field(default=None, ge=0, le=3)
    source: Literal["file", "text"] | None = None
    created_after: datetime | None = None
    has_skills_section: bool | None = None
    # Substring the indexed text must contain -- a where_document filter, so it
    # can insist on a literal term the embedding may have generalised away.
    must_contain: str | None = Field(default=None, max_length=200)


class SearchRequest(BaseModel):
    """Search one collection using the other side as the query.

    Give either `query_id` (an existing document of the opposite kind, whose
    stored vector is reused) or `query_text` (embedded on the fly).
    """

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
    # Echo of the metadata conditions Chroma actually applied.
    filters_applied: list[str]
    query_kind: str
    searched_kind: str


class VectorStatsResponse(BaseModel):
    """Per-user counts, read straight out of Chroma with a metadata filter."""

    resume_vectors: int
    jd_vectors: int
    mode: str
