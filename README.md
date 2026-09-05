# Resume–JD Matcher

Upload a resume and a job description. Get a **match score** and a short written
explanation of why the fit looks strong or weak.

A portfolio project: a full upload → score → explain pipeline that runs on free
tiers — not a research-grade matcher.

---

## What it does

1. **Upload** a resume (PDF / DOCX / TXT) and a job description (file or paste).
2. **Match** the pair — five signals blended into one score.
3. **Explain** strengths and gaps, grounded in the most relevant resume excerpts.
4. **History** of past matches for your account.

---

## How scoring works

```
resume + JD
     │
     ▼
  parse          pdfplumber / docx2txt → plain text → rough section split
     │
     ▼
  embed          all-MiniLM-L6-v2 (384-dim), stored on the Mongo document
     │
     ├── cosine similarity .............. cheap semantic baseline
     ├── cross-encoder .................. reads both texts together
     └── keyword / years / education .... simple, explainable features
     │
     ▼
  score          weighted sum of the five signals
     │
     ▼
  explain        top resume chunks → Groq or Gemini (template if no API key)
```

### Why two models

| Model | Role |
|-------|------|
| **Bi-encoder** (MiniLM) | Embeds each document alone. Vectors are cached; cosine is one cheap compare. |
| **Cross-encoder** (ms-marco MiniLM) | Reads resume + JD as a pair. Better at true relevance; only runs on the chosen pair. |

Cosine can still give a non-zero score to unrelated “job-shaped” documents.
The cross-encoder separates those cases more clearly, which is why it gets the
highest weight in the final score.

### Score weights

| Signal | Weight |
|--------|--------|
| Cross-encoder | 0.45 |
| Cosine similarity | 0.25 |
| Keyword overlap | 0.15 |
| Years of experience | 0.10 |
| Education | 0.05 |

These weights are a hand-picked starting point, not a fitted model.

---

## Stack

| Layer | Choice |
|-------|--------|
| API | FastAPI |
| Database | MongoDB (Atlas free tier works) |
| Auth | bcrypt passwords + JWT |
| ML | sentence-transformers (CPU) |
| Explanations | Groq → Gemini → keyword template |
| Frontend | Plain HTML / CSS / JS (no framework) |
| Run | Docker Compose (nginx + backend) |

---

## Run it

### 1. MongoDB

Create a free Atlas cluster (or use local Mongo). Copy the connection string.

### 2. Configure

```bash
cp .env.example .env
```

Set at least:

- `MONGODB_URI`
- `JWT_SECRET` — e.g. `python -c "import secrets; print(secrets.token_hex(32))"`

LLM keys are optional. Without them, the app still scores and falls back to a
keyword-gap template for the explanation.

### 3. Start

```bash
docker compose up --build
```

| | URL |
|--|-----|
| App | http://localhost:8080 |
| API docs | http://localhost:8080/api/docs |

nginx serves the UI and proxies `/api` to the backend, so the browser talks to
one origin.

The first build downloads the ML models into the image (~a few minutes). Later
starts are fast.

<details>
<summary>Without Docker</summary>

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then serve the `frontend/` folder, or use the API at http://localhost:8000/docs.
</details>

---

## Project layout

```
backend/app/
  main.py          FastAPI entry; warms models on startup
  config.py        settings from .env
  db.py            Mongo client + collections
  auth.py          passwords, JWT, current_user
  schemas.py       request / response models
  routers/
    auth_routes.py     signup / login
    documents.py       upload & list resumes / JDs
    match_routes.py    score a pair + explanation
  services/
    parsing.py         file → text → sections
    embeddings.py      embed / cosine / cross-encode
    features.py        keywords, years, education
    scoring.py         weighted final score
    retrieval.py       top chunks for the LLM
    explain.py         Groq → Gemini → template
frontend/
  index.html, style.css, api.js, app.js
```

See [BUILD_SEQUENCE.md](BUILD_SEQUENCE.md) for the order to build these files
from scratch.

---

## Design notes

**Tenant isolation** — every Mongo query includes `user_id` in the filter, not
as a check after fetch. Another user’s resume simply never comes back.

**Explanations stay grounded** — the LLM only sees the top resume chunks
relevant to the JD, plus missing keywords. It is told not to invent experience.

**No LLM key required** — scoring always works; explanation degrades to a clear
template listing JD terms missing from the resume.

---

## Tests

```bash
cd backend && python -m pytest tests -q
```

Covers auth, duplicate signup, tenant isolation, the full upload → match flow,
and upload validation.

---

## Known limits

- Section headers are keyword-matched; messy two-column PDFs often land in `other` (full-text matching still works).
- No OCR — scanned image PDFs are rejected.
- Years are parsed with a regex for “N years”, not date ranges like 2019–2025.
- Free-tier hosts may cold-start while models load.
