"""Create and read matches."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.db import jds, matches, resumes
from app.schemas import MatchOut, MatchRequest
from app.services.embeddings import cosine, cross_encode
from app.services.explain import generate_explanation
from app.services.scoring import score_pair

router = APIRouter(prefix="/matches", tags=["matches"])


def _object_id(value: str, label: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId:
        raise HTTPException(400, f"Invalid {label}.")


def _as_match_out(doc: dict) -> MatchOut:
    return MatchOut(
        id=str(doc["_id"]),
        resume_id=str(doc["resume_id"]),
        jd_id=str(doc["jd_id"]),
        cosine_score=doc["cosine_score"],
        cross_encoder_score=doc["cross_encoder_score"],
        final_score=doc["final_score"],
        features=doc.get("features", {}),
        explanation_text=doc.get("explanation_text", ""),
        created_at=doc["created_at"],
    )


@router.post("", response_model=MatchOut, status_code=201)
async def create_match(body: MatchRequest, user: dict = Depends(current_user)):
    # user_id in the filter, not checked after the fetch -- a document
    # belonging to someone else simply doesn't exist as far as this query is
    # concerned, so there's no path where we read it and forget to compare.
    resume = await resumes().find_one(
        {"_id": _object_id(body.resume_id, "resume id"), "user_id": user["_id"]}
    )
    if resume is None:
        raise HTTPException(404, "Resume not found.")

    jd = await jds().find_one(
        {"_id": _object_id(body.jd_id, "JD id"), "user_id": user["_id"]}
    )
    if jd is None:
        raise HTTPException(404, "Job description not found.")

    resume_text, jd_text = resume["parsed_text"], jd["parsed_text"]

    cosine_score = cosine(resume["embedding"], jd["embedding"])
    cross_score = cross_encode(resume_text, jd_text)
    final_score, features, scorer = score_pair(
        resume_text, jd_text, cosine_score, cross_score
    )
    explanation = await generate_explanation(resume_text, jd_text, final_score)

    doc = {
        "user_id": user["_id"],
        "resume_id": resume["_id"],
        "jd_id": jd["_id"],
        "cosine_score": round(cosine_score, 4),
        "cross_encoder_score": round(cross_score, 4),
        "final_score": final_score,
        # Stored so the retraining script can rebuild this exact training row
        # later, even if the feature code changes in the meantime.
        "features": features,
        "scorer": scorer,
        "explanation_text": explanation,
        "created_at": datetime.now(timezone.utc),
    }
    result = await matches().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _as_match_out(doc)


@router.get("", response_model=list[MatchOut])
async def list_matches(user: dict = Depends(current_user)):
    cursor = matches().find({"user_id": user["_id"]}).sort("created_at", -1).limit(50)
    return [_as_match_out(doc) async for doc in cursor]


@router.get("/{match_id}", response_model=MatchOut)
async def get_match(match_id: str, user: dict = Depends(current_user)):
    doc = await matches().find_one(
        {"_id": _object_id(match_id, "match id"), "user_id": user["_id"]}
    )
    if doc is None:
        raise HTTPException(404, "Match not found.")
    return _as_match_out(doc)
