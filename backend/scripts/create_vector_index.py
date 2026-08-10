import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo.operations import SearchIndexModel

from app.config import settings
from app.db import close_client, get_db


INDEX_NAME = "embedding_index"


def get_index_definition() -> dict:
    """Return the configuration used for MongoDB vector search."""

    return {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": settings.embedding_dim,
                "similarity": "cosine",
            },
            # Allows MongoDB to filter results by user before
            # performing the vector search.
            {
                "type": "filter",
                "path": "user_id",
            },
        ]
    }


async def create_index(collection_name: str) -> None:
    """Create the vector search index for a collection if needed."""

    collection = get_db()[collection_name]

    indexes = [
        index["name"]
        async for index in await collection.list_search_indexes()
    ]

    if INDEX_NAME in indexes:
        print(f"{collection_name}: {INDEX_NAME} already exists")
        return

    index_model = SearchIndexModel(
        definition=get_index_definition(),
        name=INDEX_NAME,
        type="vectorSearch",
    )

    await collection.create_search_index(index_model)

    print(
        f"{collection_name}: created {INDEX_NAME}. "
        "MongoDB will build it in the background."
    )


async def main() -> None:
    print(
        f"Creating vector search indexes "
        f"for database: {settings.mongodb_db}"
    )

    try:
        for collection_name in ("resumes", "jds"):
            await create_index(collection_name)

        print("\nDone.")
        print("The indexes may take a little while to finish building.")

    except Exception as exc:
        print(f"\nFailed to create indexes: {exc}")
        print(
            "The application can still work using "
            "Python-based cosine similarity as a fallback."
        )

    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())