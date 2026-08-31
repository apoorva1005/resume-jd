#In this application, it manages two types of vector data: resumes and job descriptions.
# It first creates or connects to ChromaDB using one of three modes—memory, HTTP, or persistent local storage—
# caches the client and collections so they can be reused. 
#It provides functions to insert/update embeddings (upsert), insert multiple embeddings at once, delete vectors,
# retrieve embeddings, count stored vectors, and most importantly perform similarity searches (query) using embeddings 
#and cosine distance. Since ChromaDB operations are synchronous but FastAPI is asynchronous, 
#the file uses asyncio.to_thread() so ChromaDB work runs in a separate thread without blocking FastAPI's event loop. 
#It also converts ChromaDB's raw search results into a simpler VectorHit object containing the ID, similarity score, document, and metadata,
# and provides health() and ensure_collections() functions to check whether ChromaDB is available


from __future__ import annotations#handle type annotations more flexibly
import asyncio
import logging

from typing import Any
import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from app.config import settings


log = logging.getLogger(__name__)
RESUME = "resume"
JD = "jd"
_client: ClientAPI | None = None
_collections: dict[str, Collection] = {}

_unavailable_reason: str | None = None

class VectorHit:
    def __init__(
        self,
        id: str,
        similarity: float,
        document: str,
        metadata: dict[str, Any],
    ):
        self.id = id
        self.similarity = similarity
        self.document = document
        self.metadata = metadata
#usually 3 modes of operation how chroma runs
#1. memory: in-memory only, no persistence
#2. http: connect to a remote ChromaDB instance
#3. persistent: save data to a local directory
#here we are using the persistent mode
def _build_client() -> ClientAPI:
    mode = settings.chroma_mode.lower()

    if mode == "memory":
        return chromadb.EphemeralClient()

    if mode == "http":
        return chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            ssl=settings.chroma_ssl,
        )

    if mode == "persistent":
        return chromadb.PersistentClient(
            path=settings.chroma_path
        )

    raise ValueError(
        f"Unknown CHROMA_MODE {settings.chroma_mode!r}. "
        "Use 'memory', 'persistent' or 'http'."
    )


def get_client() -> ClientAPI:
    global _client, _unavailable_reason

    if _client is None:
        _client = _build_client()
        _unavailable_reason = None

    return _client


def reset_client() -> None:
    global _client, _unavailable_reason
    _client = None
    _unavailable_reason = None
    _collections.clear()


def collection_name(kind: str) -> str:
    if kind == RESUME:
        return settings.chroma_resume_collection

    if kind == JD:
        return settings.chroma_jd_collection

    raise ValueError(
        f"kind must be {RESUME!r} or {JD!r}, got {kind!r}"
    )


def _collection(kind: str) -> Collection:
    cached_collection = _collections.get(kind)

    if cached_collection is not None:
        return cached_collection

    collection = get_client().get_or_create_collection(
        name=collection_name(kind),
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,
    )

    _collections[kind] = collection

    return collection

#ChromaDB operations in this implementation are synchronous, 
#so I use asyncio.to_thread() to execute them in a worker thread 
#and avoid blocking FastAPI's async event loop
async def _run(fn, *args, **kwargs):
    global _unavailable_reason

    try:
        result = await asyncio.to_thread(fn, *args, **kwargs)

    except Exception as exc:
        _unavailable_reason = f"{type(exc).__name__}: {exc}"
        raise
    _unavailable_reason = None

    return result


async def upsert(
    kind: str,
    doc_id: str,
    embedding: list[float],
    document: str,
    metadata: dict[str, Any],
) -> None:
    def _work() -> None:
        _collection(kind).upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )

    await _run(_work)


async def upsert_many(
    kind: str,
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    if not ids:
        return

    def _work() -> None:
        _collection(kind).upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    await _run(_work)


async def try_upsert(
    kind: str,
    doc_id: str,
    embedding: list[float],
    document: str,
    metadata: dict[str, Any],
) -> bool:
    try:
        await upsert(
            kind=kind,
            doc_id=doc_id,
            embedding=embedding,
            document=document,
            metadata=metadata,
        )
        return True

    except Exception as exc:
        log.warning(
            "ChromaDB upsert failed for %s %s: %s",
            kind,
            doc_id,
            exc,
        )
        return False


async def delete(
    kind: str,
    doc_id: str,
    user_id: str,
) -> None:
    def _work() -> None:
        _collection(kind).delete(
            ids=[doc_id],
            where={"user_id": user_id},
        )

    await _run(_work)


async def query(
    kind: str,
    embedding: list[float],
    k: int,
    where: dict[str, Any],
    where_document: dict[str, Any] | None = None,
) -> list[VectorHit]:
    def _work():
        return _collection(kind).query(
            query_embeddings=[embedding],
            n_results=max(1, k),
            where=where or None,
            where_document=where_document or None,
            include=["metadatas", "documents", "distances"],
        )

    query_result = await _run(_work)

    return _to_hits(query_result)


def _to_hits(result: dict[str, Any]) -> list[VectorHit]:
    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]

    hits: list[VectorHit] = []

    for index, doc_id in enumerate(ids):
        distance = (
            distances[index]
            if index < len(distances)
            else None
        )

        document = (
            documents[index]
            if index < len(documents)
            else ""
        )

        metadata = (
            dict(metadatas[index] or {})
            if index < len(metadatas)
            else {}
        )

        hits.append(
            VectorHit(
                id=str(doc_id),
                similarity=_similarity(distance),
                document=document,
                metadata=metadata,
            )
        )

    return hits


def _similarity(distance: float | None) -> float:
    if distance is None:
        return 0.0

    similarity = 1.0 - float(distance)
    similarity = max(0.0, min(1.0, similarity))

    return round(similarity, 4)


async def get_embedding(
    kind: str,
    doc_id: str,
    user_id: str,
) -> list[float] | None:
    def _work():
        return _collection(kind).get(
            ids=[doc_id],
            where={"user_id": user_id},
            include=["embeddings"],
        )

    result = await _run(_work)

    embeddings = result.get("embeddings")

    if not embeddings:
        return None

    # ChromaDB may return a NumPy array or a normal Python list.
    first_embedding = embeddings[0]

    if hasattr(first_embedding, "tolist"):
        return first_embedding.tolist()

    return list(first_embedding)


async def count(
    kind: str,
    where: dict[str, Any] | None = None,
) -> int:
    def _work() -> int:
        collection = _collection(kind)

        if not where:
            return collection.count()

        matching_documents = collection.get(
            where=where,
            include=[],
        )

        return len(matching_documents.get("ids") or [])

    return await _run(_work)


async def ensure_collections() -> bool:
    def _work() -> None:
        for kind in (RESUME, JD):
            _collection(kind)

    try:
        await _run(_work)
        return True

    except Exception as exc:
        log.warning(
            "ChromaDB unavailable at startup (mode=%s): %s. "
            "Uploads will still succeed; vector search will return "
            "503 until ChromaDB becomes available again.",
            settings.chroma_mode,
            exc,
        )
        return False


async def health() -> dict[str, Any]:
    status: dict[str, Any] = {
        "mode": settings.chroma_mode,
        "collections": {
            RESUME: settings.chroma_resume_collection,
            JD: settings.chroma_jd_collection,
        },
    }

    try:
        status["resume_vectors"] = await count(RESUME)
        status["jd_vectors"] = await count(JD)
        status["connected"] = True

    except Exception as exc:
        status["connected"] = False
        status["error"] = (
            _unavailable_reason
            or f"{type(exc).__name__}: {exc}"
        )

    return status