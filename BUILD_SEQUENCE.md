# Build sequence

Order to create files when building Resume–JD Matcher from scratch, with one line on what each file does.

---

## Phase 1 — Skeleton & config

| # | File | What it does |
|---|------|----------------|
| 1 | `.env.example` | Template for Mongo URI, JWT secret, and optional LLM keys |
| 2 | `.env` | Local secrets (not committed); copy from `.env.example` |
| 3 | `backend/requirements.txt` | Python dependencies for FastAPI, Mongo, ML, parsing |
| 4 | `backend/app/__init__.py` | Marks `app` as a package |
| 5 | `backend/app/config.py` | Loads settings from environment into one settings object |
| 6 | `backend/app/db.py` | Async Mongo client, collection handles, and index setup |
| 7 | `backend/app/schemas.py` | Pydantic request/response models shared by the API |

---

## Phase 2 — Auth

| # | File | What it does |
|---|------|----------------|
| 8 | `backend/app/auth.py` | bcrypt password hashing, JWT issue/verify, `current_user` dependency |
| 9 | `backend/app/routers/__init__.py` | Marks `routers` as a package |
| 10 | `backend/app/routers/auth_routes.py` | Signup and login endpoints |
| 11 | `backend/app/main.py` | FastAPI entrypoint: lifespan, CORS, mounts routers, `/health` |

---

## Phase 3 — ML services (pure logic, no HTTP)

| # | File | What it does |
|---|------|----------------|
| 12 | `backend/app/services/__init__.py` | Marks `services` as a package |
| 13 | `backend/app/services/parsing.py` | Turns PDF/DOCX into plain text and rough resume sections |
| 14 | `backend/app/services/embeddings.py` | Bi-encoder embed, cosine similarity, and cross-encoder score |
| 15 | `backend/app/services/features.py` | Keyword overlap, years-of-experience, and education signals |
| 16 | `backend/app/services/scoring.py` | Weighted sum of features, or trained logistic ranker if present |
| 17 | `backend/app/services/retrieval.py` | Chunks the resume and picks top-k chunks for the explanation |
| 18 | `backend/app/services/explain.py` | LLM explanation (Groq → Gemini) or keyword-gap template fallback |

---

## Phase 4 — API routes

| # | File | What it does |
|---|------|----------------|
| 19 | `backend/app/routers/documents.py` | Upload/list resumes and JDs; parse, embed, store in Mongo |
| 20 | `backend/app/routers/match_routes.py` | Score a resume–JD pair and return the explanation |
| 21 | `backend/app/routers/feedback_routes.py` | Save thumbs or a corrected score for a match |

---

## Phase 5 — Frontend

| # | File | What it does |
|---|------|----------------|
| 22 | `frontend/index.html` | Page markup: auth, upload, match, feedback, history |
| 23 | `frontend/style.css` | Layout and styling (no CSS framework) |
| 24 | `frontend/api.js` | Fetch wrapper to `/api`, JWT in localStorage |
| 25 | `frontend/app.js` | UI logic: tabs, upload, match, feedback, history |

---

## Phase 6 — Scripts, tests, deploy

| # | File | What it does |
|---|------|----------------|
| 26 | `backend/scripts/dev_server.py` | Serves the frontend and proxies `/api` for non-Docker local run |
| 27 | `backend/scripts/create_vector_index.py` | Creates the optional Atlas Vector Search index |
| 28 | `backend/scripts/retrain_ranker.py` | Trains logistic regression from feedback into `ranker.joblib` |
| 29 | `backend/tests/test_api.py` | API tests: auth, tenant isolation, upload → match → feedback |
| 30 | `frontend/test_render.js` | Checks HTML escaping and markdown render helpers |
| 31 | `backend/Dockerfile` | Builds the backend image (includes ML models) |
| 32 | `frontend/Dockerfile` | Builds the nginx image that serves static files |
| 33 | `frontend/nginx.conf` | Serves the SPA and proxies `/api` to the backend |
| 34 | `docker-compose.yml` | Runs frontend + backend together |
| 35 | `README.md` | How it works, how to run, design notes |

---

## Dependency flow

```
config → db → schemas
              ↓
            auth → auth_routes → main
              ↓
 parsing → embeddings → features → scoring → retrieval → explain
              ↓
     documents → match_routes → feedback_routes
              ↓
     index.html → style.css → api.js → app.js
              ↓
     scripts → tests → Docker → README
```
