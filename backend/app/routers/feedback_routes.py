"""Collect user feedback on a match. This is the training data for step 7."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.db import feedback, matches
from app.schemas import FeedbackRequest

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", status_code=201)
async def submit_feedback(body: FeedbackRequest, user: dict = Depends(current_user)):
    try:
        match_oid = ObjectId(body.match_id)
    except InvalidId:
        raise HTTPException(400, "Invalid match id.")

    # Confirm the match belongs to this user before accepting feedback on it,
    # otherwise anyone could poison another tenant's training data.
    match = await matches().find_one({"_id": match_oid, "user_id": user["_id"]})
    if match is None:
        raise HTTPException(404, "Match not found.")

    doc = {
        "match_id": match_oid,
        "user_id": user["_id"],
        "user_rating": body.user_rating,
        "corrected_score": body.corrected_score,
        "comment": body.comment[:1000],
        "created_at": datetime.now(timezone.utc),
    }

    # One feedback row per user per match -- resubmitting updates rather than
    # stacking duplicates, so a user can't skew training by clicking twice.
    await feedback().replace_one(
        {"match_id": match_oid, "user_id": user["_id"]}, doc, upsert=True
    )
    return {"status": "recorded"}


@router.get("/{match_id}")
async def get_feedback(match_id: str, user: dict = Depends(current_user)):
    try:
        match_oid = ObjectId(match_id)
    except InvalidId:
        raise HTTPException(400, "Invalid match id.")

    doc = await feedback().find_one({"match_id": match_oid, "user_id": user["_id"]})
    if doc is None:
        return {"exists": False}
    return {
        "exists": True,
        "user_rating": doc["user_rating"],
        "corrected_score": doc.get("corrected_score"),
        "comment": doc.get("comment", ""),
    }
