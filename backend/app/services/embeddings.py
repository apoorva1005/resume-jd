from functools import lru_cache

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.config import settings
MAX_CHARS = 2000


@lru_cache(maxsize=1)
def _embedder() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


@lru_cache(maxsize=1)
def _cross_encoder() -> CrossEncoder:
    return CrossEncoder(settings.cross_encoder_model)


def embed(text: str) -> list[float]:
    vector = _embedder().encode(
        text[:MAX_CHARS], normalize_embeddings=True, show_progress_bar=False
    )
    return vector.tolist()


def cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def cross_encode(resume_text: str, jd_text: str) -> float:
    raw = _cross_encoder().predict([(resume_text[:MAX_CHARS], jd_text[:MAX_CHARS])])
    return float(1 / (1 + np.exp(-raw[0])))  


def warm_up() -> None:
    _embedder()
    _cross_encoder()
