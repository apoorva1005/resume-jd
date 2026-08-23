import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import vectorstore
from app.config import settings
from app.db import close_client, jds, resumes
from app.services.vector_search import build_metadata, indexed_document

BATCH_SIZE = 200
async def reindex(kind: str, collection, force: bool) -> tuple[int, int]:
    query = {} if force else {"indexed": {"$ne": True}}

    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    mongo_ids: list = []

    indexed = skipped = 0

    async def flush() -> None:
        nonlocal indexed
        if not ids:
            return
        await vectorstore.upsert_many(kind, ids, embeddings, documents, metadatas)
        # Only mark documents indexed once the upsert actually returned, so a
        # crash mid-run leaves them to be retried rather than silently skipped.
        await collection.update_many(
            {"_id": {"$in": mongo_ids}}, {"$set": {"indexed": True}}
        )
        indexed += len(ids)
        print(f"  {kind}: {indexed} indexed so far")
        ids.clear()
        embeddings.clear()
        documents.clear()
        metadatas.clear()
        mongo_ids.clear()

    async for doc in collection.find(query):
        embedding = doc.get("embedding")
        text = doc.get("parsed_text") or ""
        if not embedding or not text:
            # Nothing to index and nothing this script can recover -- the
            # document would need re-embedding, which is the upload path's job.
            skipped += 1
            continue

        ids.append(str(doc["_id"]))
        embeddings.append(embedding)
        documents.append(indexed_document(text))
        metadatas.append(
            build_metadata(
                kind=kind,
                user_id=str(doc["user_id"]),
                text=text,
                created_at=doc["created_at"],
                filename=doc.get("filename") or "",
                sections=doc.get("sections"),
            )
        )
        mongo_ids.append(doc["_id"])

        if len(ids) >= BATCH_SIZE:
            await flush()

    await flush()
    return indexed, skipped


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="re-upsert every document, not just ones missing from the index",
    )
    args = parser.parse_args()

    print(f"Mongo:  {settings.mongodb_db}")
    print(f"Chroma: mode={settings.chroma_mode}", end="")
    if settings.chroma_mode == "http":
        print(f" host={settings.chroma_host}:{settings.chroma_port}")
    elif settings.chroma_mode == "persistent":
        print(f" path={settings.chroma_path}")
    else:
        print(" (in-memory -- nothing will persist)")

    if not await vectorstore.ensure_collections():
        print("\nCould not reach Chroma. Check CHROMA_MODE and the host/port.")
        await close_client()
        raise SystemExit(1)

    try:
        total_indexed = 0
        for kind, collection in ((vectorstore.RESUME, resumes), (vectorstore.JD, jds)):
            print(f"\n{kind}s:")
            indexed, skipped = await reindex(kind, collection(), args.all)
            total_indexed += indexed
            print(f"  done: {indexed} indexed, {skipped} skipped (no embedding)")

        print(f"\n{total_indexed} vector(s) written.")
        for kind in (vectorstore.RESUME, vectorstore.JD):
            print(
                f"  {vectorstore.collection_name(kind)}: "
                f"{await vectorstore.count(kind)} total"
            )
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
