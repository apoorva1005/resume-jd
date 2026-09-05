# Build sequence

Order to create files when building Resume–JD Matcher from scratch.

---

## Phase 1 — Config & data

| # | File | What it does |
|---|------|----------------|
| 1 | `.env.example` | Mongo URI, JWT secret, optional LLM keys |
| 2 | `.env` | Local secrets (not committed) |
| 3 | `backend/requirements.txt` | Python dependencies |
| 4 | `backend/app/__init__.py` | Marks `app` as a package |
| 5 | `backend/app/config.py` | Loads settings from environment |
| 6 | `backend/app/db.py` | Async Mongo client and collections |
| 7 | `backend/app/schemas.py` | Request/response models |

---

## Phase 2 — Auth

| # | File | What it does |
|---|------|----------------|
| 8 | `backend/app/auth.py` | bcrypt + JWT + `current_user` |
| 9 | `backend/app/routers/__init__.py` | Marks `routers` as a package |
| 10 | `backend/app/routers/auth_routes.py` | Signup and login |
| 11 | `backend/app/main.py` | FastAPI app, routers, static UI, `/health` |

---

## Phase 3 — ML services

| # | File | What it does |
|---|------|----------------|
| 12 | `backend/app/services/__init__.py` | Marks `services` as a package |
| 13 | `backend/app/services/parsing.py` | PDF/DOCX/TXT → text → sections |
| 14 | `backend/app/services/embeddings.py` | Embed, cosine, cross-encoder |
| 15 | `backend/app/services/features.py` | Keyword, years, education signals |
| 16 | `backend/app/services/scoring.py` | Weighted sum of five signals |
| 17 | `backend/app/services/retrieval.py` | Top resume chunks for explanation |
| 18 | `backend/app/services/explain.py` | Groq → Gemini → template fallback |

---

## Phase 4 — API routes

| # | File | What it does |
|---|------|----------------|
| 19 | `backend/app/routers/documents.py` | Upload and list resumes / JDs |
| 20 | `backend/app/routers/match_routes.py` | Score a pair and return explanation |

---

## Phase 5 — Frontend

| # | File | What it does |
|---|------|----------------|
| 21 | `frontend/index.html` | Auth, upload, match, history |
| 22 | `frontend/style.css` | Layout and styling |
| 23 | `frontend/api.js` | Fetch wrapper + JWT |
| 24 | `frontend/app.js` | UI logic |

---

## Phase 6 — Tests & deploy

| # | File | What it does |
|---|------|----------------|
| 25 | `backend/tests/test_api.py` | Auth, isolation, upload → match |
| 26 | `backend/Dockerfile` | Image with API, UI, and ML models |
| 27 | `docker-compose.yml` | Single backend service on port 8080 |
| 28 | `README.md` | How it works and how to run |

---

## Dependency flow

```
config → db → schemas
           ↓
         auth → auth_routes → main (+ StaticFiles)
           ↓
parsing → embeddings → features → scoring → retrieval → explain
           ↓
     documents → match_routes
           ↓
     index.html → style.css → api.js → app.js
           ↓
     tests → Docker → README
```
