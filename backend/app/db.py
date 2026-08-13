#This file is the database connection and MongoDB utility file 
from gridfs.asynchronous import AsyncGridFSBucket
#GridFS is MongoDB's system for storing large files.
from pymongo import AsyncMongoClient
#Connecting your Python application to MongoDB.
from app.config import settings

_client: AsyncMongoClient | None = None
#initially client is none

def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(settings.mongodb_uri)
    return _client


def get_db():
    return get_client()[settings.mongodb_db]


def get_bucket() -> AsyncGridFSBucket:
    
    return AsyncGridFSBucket(get_db())

def users():
    return get_db()["users"]


def resumes():
    return get_db()["resumes"]


def jds():
    return get_db()["jds"]


def matches():
    return get_db()["matches"]


def feedback():
    return get_db()["feedback"]

#1 ascendin
async def ensure_indexes() -> None:
    await users().create_index("email", unique=True)
    await resumes().create_index([("user_id", 1), ("created_at", -1)])
    await jds().create_index([("user_id", 1), ("created_at", -1)])
    await matches().create_index([("user_id", 1), ("created_at", -1)])
    await feedback().create_index("match_id")


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
