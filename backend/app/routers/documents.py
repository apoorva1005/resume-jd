"""Upload and list resumes / JDs.

Note the user_id filter on every read. MongoDB has no row-level security, so
tenant isolation lives here in application code -- see the README.
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth import current_user
from app.db import get_bucket, jds, resumes
from app.schemas import DocumentOut
from app.services.embeddings import embed
from app.services.parsing import clean_text, extract_text, split_sections

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB; resumes are never bigger than this


def _as_document_out(doc: dict, kind: str) -> DocumentOut:
    return DocumentOut(
        id=str(doc["_id"]),
        kind=kind,
        preview=doc["parsed_text"][:200],
        created_at=doc["created_at"],
    )


async def _store_file(upload: UploadFile, user_id: ObjectId) -> tuple[ObjectId, str]:
    """Save to GridFS, return (file_id, extracted text)."""
    data = await upload.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 5MB.")

    try:
        text = clean_text(extract_text(data, upload.filename or "upload"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if len(text) < 50:
        raise HTTPException(
            400, "Could not read enough text from that file. Is it a scanned image?"
        )

    file_id = await get_bucket().upload_from_stream(
        upload.filename or "upload",
        data,
        metadata={"user_id": user_id, "content_type": upload.content_type},
    )
    return file_id, text


@router.post("/resumes", response_model=DocumentOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...), user: dict = Depends(current_user)
):
    file_id, text = await _store_file(file, user["_id"])
    doc = {
        "user_id": user["_id"],
        "file_id": file_id,
        "parsed_text": text,
        "sections": split_sections(text),
        "embedding": embed(text),
        "created_at": datetime.now(timezone.utc),
    }
    result = await resumes().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _as_document_out(doc, "resume")


@router.post("/jds", response_model=DocumentOut, status_code=201)
async def upload_jd(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    user: dict = Depends(current_user),
):
    """A JD can be pasted as text or uploaded as a file."""
    if file is not None and file.filename:
        file_id, parsed = await _store_file(file, user["_id"])
    elif text.strip():
        file_id, parsed = None, clean_text(text)
    else:
        raise HTTPException(400, "Provide a JD file or paste the text.")

    if len(parsed) < 50:
        raise HTTPException(400, "That job description is too short to match on.")

    doc = {
        "user_id": user["_id"],
        "file_id": file_id,
        "parsed_text": parsed,
        "embedding": embed(parsed),
        "created_at": datetime.now(timezone.utc),
    }
    result = await jds().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _as_document_out(doc, "jd")


@router.get("/resumes", response_model=list[DocumentOut])
async def list_resumes(user: dict = Depends(current_user)):
    cursor = resumes().find({"user_id": user["_id"]}).sort("created_at", -1).limit(50)
    return [_as_document_out(doc, "resume") async for doc in cursor]


@router.get("/jds", response_model=list[DocumentOut])
async def list_jds(user: dict = Depends(current_user)):
    cursor = jds().find({"user_id": user["_id"]}).sort("created_at", -1).limit(50)
    return [_as_document_out(doc, "jd") async for doc in cursor]
