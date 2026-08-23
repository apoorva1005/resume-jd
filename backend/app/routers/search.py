from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from app import vectorstore
from app.auth import current_user
from app.config import settings
from app.db import jds, resumes
from app.schemas import (
    SearchHit,
    SearchRequest,
    SearchResponse,
    VectorStatsResponse,
)
from app.services.embeddings import embed
from app.services.vector_search import (
    PREVIEW_CHARS,
    build_where,
    build_where_document,
    describe_filters,
)

router = APIRouter(prefix="/search", tags=["search"])

_COLLECTION_FOR = {vectorstore.RESUME: resumes, vectorstore.JD: jds}


async def _query_vector(
    body: SearchRequest, query_kind: str, user_id: ObjectId
) -> list[float]:
    if body.query_id:
        try:
            oid = ObjectId(body.query_id)
        except InvalidId:
            raise HTTPException(400, "Invalid query_id.")

        doc = await _COLLECTION_FOR[query_kind]().find_one(
            {"_id": oid, "user_id": user_id}
        )
        if doc is None:
            raise HTTPException(404, f"No {query_kind} found with that id.")

        embedding = doc.get("embedding")
        if embedding:
            return embedding

        # Pre-Chroma documents, or one whose vector never made it into Mongo.
        stored = await vectorstore.get_embedding(query_kind, str(oid), str(user_id))
        if stored is None:
            raise HTTPException(409, "That document has no embedding yet.")
        return stored

    if body.query_text and body.query_text.strip():
        return embed(body.query_text)

    raise HTTPException(400, "Provide either query_id or query_text.")


async def _search(
    body: SearchRequest, searched_kind: str, query_kind: str, user: dict
) -> SearchResponse:
    user_id = user["_id"]
    embedding = await _query_vector(body, query_kind, user_id)

    # user_id is folded in here, not checked afterwards: another tenant's
    # document is never a candidate for the nearest-neighbour search at all.
    where = build_where(str(user_id), body.filters)
    where_document = build_where_document(body.filters)

    try:
        hits = await vectorstore.query(
            kind=searched_kind,
            embedding=embedding,
            k=body.k,
            where=where,
            where_document=where_document,
        )
    except Exception as exc:
        raise HTTPException(
            503,
            "Vector search is unavailable right now "
            f"(Chroma mode={settings.chroma_mode}): {exc}",
        )

    return SearchResponse(
        hits=[_as_hit(hit, searched_kind) for hit in hits],
        count=len(hits),
        filters_applied=describe_filters(where)
        + ([f"text contains {body.filters.must_contain!r}"] if where_document else []),
        query_kind=query_kind,
        searched_kind=searched_kind,
    )


def _as_hit(hit: vectorstore.VectorHit, kind: str) -> SearchHit:
    metadata = hit.metadata
    return SearchHit(
        id=hit.id,
        kind=kind,
        similarity=hit.similarity,
        preview=hit.document[:PREVIEW_CHARS],
        created_at=metadata.get("created_at"),
        years_experience=metadata.get("years_experience"),
        degree_rank=metadata.get("degree_rank"),
        source=metadata.get("source"),
        filename=metadata.get("filename") or None,
    )


@router.post("/resumes", response_model=SearchResponse)
async def search_resumes(body: SearchRequest, user: dict = Depends(current_user)):
    """Rank your resumes against a JD (by id) or arbitrary text."""
    return await _search(
        body,
        searched_kind=vectorstore.RESUME,
        query_kind=vectorstore.JD,
        user=user,
    )


@router.post("/jds", response_model=SearchResponse)
async def search_jds(body: SearchRequest, user: dict = Depends(current_user)):
    """Rank your job descriptions against a resume (by id) or arbitrary text."""
    return await _search(
        body,
        searched_kind=vectorstore.JD,
        query_kind=vectorstore.RESUME,
        user=user,
    )


@router.get("/stats", response_model=VectorStatsResponse)
async def vector_stats(user: dict = Depends(current_user)):
    where = {"user_id": {"$eq": str(user["_id"])}}
    try:
        return VectorStatsResponse(
            resume_vectors=await vectorstore.count(vectorstore.RESUME, where),
            jd_vectors=await vectorstore.count(vectorstore.JD, where),
            mode=settings.chroma_mode,
        )
    except Exception as exc:
        raise HTTPException(503, f"Vector store is unavailable: {exc}")
