import httpx

from app.config import settings
from app.services.features import missing_keywords
from app.services.retrieval import top_chunks

TIMEOUT = 30.0

SYSTEM_PROMPT = """You are a hiring assistant. Compare a candidate's resume \
against a job description.

Rules:
- Use ONLY the resume excerpts provided. Never invent experience, employers, \
or skills that are not in the text.
- If the excerpts don't cover something the job asks for, say it is not \
evidenced rather than guessing.
- Be concrete and specific. Quote or name the actual skills and roles.

Reply in exactly this shape:

**Overall:** one sentence on how well this candidate fits.

**Strengths**
- 2 to 4 bullets, each naming something from the resume that the job asks for.

**Gaps**
- 2 to 4 bullets, each naming something the job asks for that the resume does \
not evidence.

**To improve this application**
- 1 to 2 concrete, actionable suggestions."""


def build_prompt(resume_text: str, jd_text: str, score: float) -> str:
    chunks = top_chunks(resume_text, jd_text)
    excerpts = "\n\n---\n\n".join(chunks)
    gaps = ", ".join(missing_keywords(resume_text, jd_text, limit=12)) or "none found"

    return f"""JOB DESCRIPTION:
{jd_text[:2500]}

MOST RELEVANT RESUME EXCERPTS:
{excerpts[:2500]}

Terms in the job description with no match in the resume: {gaps}

The scoring model rated this match {score:.0%}. Write the explanation."""


async def _call_groq(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": settings.groq_model,
                "temperature": 0.3,  # low: this is analysis, not creative writing
                "max_tokens": 700,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


async def _call_gemini(prompt: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            url,
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 700},
            },
        )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()


def _fallback(resume_text: str, jd_text: str, score: float) -> str:
    """No-LLM explanation. Honest about being a template."""
    gaps = missing_keywords(resume_text, jd_text, limit=10)
    gap_lines = "\n".join(f"- {g}" for g in gaps) or "- No obvious keyword gaps."
    return (
        f"**Overall:** this resume scores {score:.0%} against the job description.\n\n"
        f"**Terms in the job description not found in the resume**\n{gap_lines}\n\n"
        "_(Generated without an LLM. Set GROQ_API_KEY or GEMINI_API_KEY in .env "
        "for a written explanation.)_"
    )


async def generate_explanation(resume_text: str, jd_text: str, score: float) -> str:
    prompt = build_prompt(resume_text, jd_text, score)

    if settings.groq_api_key:
        try:
            return await _call_groq(prompt)
        except Exception as exc:
            print(f"[explain] Groq failed, trying Gemini: {exc}")

    if settings.gemini_api_key:
        try:
            return await _call_gemini(prompt)
        except Exception as exc:
            print(f"[explain] Gemini failed, using template: {exc}")

    return _fallback(resume_text, jd_text, score)
