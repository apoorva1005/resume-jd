from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import vectorstore
from app.db import close_client, ensure_indexes
from app.routers import auth_routes, documents, feedback_routes, match_routes, search
from app.services.embeddings import warm_up


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    await vectorstore.ensure_collections()
    warm_up()  # download/load models now, not on the first user request
    yield
    await close_client()


app = FastAPI(title="Resume-JD Matcher", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(documents.router)
app.include_router(match_routes.router)
app.include_router(feedback_routes.router)
app.include_router(search.router)


@app.get("/health")
async def health():
    return {"status": "ok", "vector_store": await vectorstore.health()}
