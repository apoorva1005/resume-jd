import re
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "its", "of", "on", "or", "our", "that", "the",
    "to", "with", "will", "you", "your", "we", "us", "this", "these", "their",
    "work", "working", "team", "role", "job", "candidate", "experience",
    "years", "year", "ability", "strong", "excellent", "good", "including",
    "etc", "responsibilities", "requirements", "skills", "plus", "must",
}

DEGREE_RANK = {
    "phd": 3, "ph.d": 3, "doctorate": 3,
    "master": 2, "masters": 2, "msc": 2, "ms": 2, "mba": 2, "meng": 2,
    "bachelor": 1, "bachelors": 1, "bsc": 1, "bs": 1, "ba": 1, "beng": 1,
    "btech": 1, "be": 1,
}


def tokenize(text: str) -> set[str]:
   
    words = re.findall(r"[a-z0-9][a-z0-9+#.\-]*", text.lower())
    return {w.strip(".-") for w in words if len(w) > 1 and w not in STOPWORDS}


def keyword_overlap(resume_text: str, jd_text: str) -> float:
   
    jd_terms = tokenize(jd_text)
    if not jd_terms:
        return 0.0
    return len(jd_terms & tokenize(resume_text)) / len(jd_terms)


def missing_keywords(resume_text: str, jd_text: str, limit: int = 15) -> list[str]:
   
    gaps = tokenize(jd_text) - tokenize(resume_text)
    return sorted(gaps, key=len, reverse=True)[:limit]


def extract_years(text: str) -> int:
    found = re.findall(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text.lower())
    values = [int(n) for n in found if int(n) <= 50]  # 60-year careers are typos
    return max(values, default=0)


def years_match(resume_text: str, jd_text: str) -> float:
    
    required = extract_years(jd_text)
    if required == 0:
        return 0.5
    have = extract_years(resume_text)
    if have == 0:
        return 0.3  # requirement stated, resume silent -- mildly negative
    return min(have / required, 1.0)


def highest_degree(text: str) -> int:
    tokens = tokenize(text)
    return max((DEGREE_RANK.get(t, 0) for t in tokens), default=0)


def education_match(resume_text: str, jd_text: str) -> float:
    required = highest_degree(jd_text)
    if required == 0:
        return 0.5  # JD didn't ask -- neutral, same reasoning as years_match
    have = highest_degree(resume_text)
    if have >= required:
        return 1.0
    return 0.5 if have > 0 else 0.0


def build_features(resume_text: str, jd_text: str) -> dict[str, float]:
   
    return {
        "keyword_overlap": round(keyword_overlap(resume_text, jd_text), 4),
        "years_match": round(years_match(resume_text, jd_text), 4),
        "education_match": round(education_match(resume_text, jd_text), 4),
    }
