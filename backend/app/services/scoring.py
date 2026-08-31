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
    "keyword_overlap": 0.15,
    "years_match": 0.10,
    "education_match": 0.05,
}
assert set(DEFAULT_WEIGHTS) == set(FEATURE_ORDER), "weights must cover every feature"


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
    return round(weighted_score(values), 4), values, "weighted_sum"
