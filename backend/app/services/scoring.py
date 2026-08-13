import os
from pathlib import Path

import joblib

from app.config import settings
from app.services.features import build_features
FEATURE_ORDER = [
    "cosine_score",
    "cross_encoder_score",
    "keyword_overlap",
    "years_match",
    "education_match",
]

DEFAULT_WEIGHTS = {
    "cosine_score": 0.25,
    "cross_encoder_score": 0.45,  
    "years_match": 0.10,
    "education_match": 0.05,
}

_ranker = None
_ranker_mtime: float | None = None


def load_ranker():
    global _ranker, _ranker_mtime

    path = Path(settings.ranker_path)
    if not path.exists():
        _ranker, _ranker_mtime = None, None
        return None

    mtime = os.path.getmtime(path)
    if _ranker is None or mtime != _ranker_mtime:
        try:
            _ranker = joblib.load(path)
            _ranker_mtime = mtime
        except Exception:
            _ranker, _ranker_mtime = None, None
    return _ranker


def weighted_score(values: dict[str, float]) -> float:
    return sum(DEFAULT_WEIGHTS[name] * values[name] for name in FEATURE_ORDER)


def score_pair(
    resume_text: str, jd_text: str, cosine_score: float, cross_encoder_score: float
) -> tuple[float, dict, str]:
    values = {
        "cosine_score": cosine_score,
        "cross_encoder_score": cross_encoder_score,
        **build_features(resume_text, jd_text),
    }

    ranker = load_ranker()
    if ranker is None:
        return round(weighted_score(values), 4), values, "weighted_sum"

    row = [[values[name] for name in FEATURE_ORDER]]
    try:
       final = float(ranker.predict_proba(row)[0][1])
    except Exception:
        return round(weighted_score(values), 4), values, "weighted_sum"

    return round(final, 4), values, "trained_ranker"
