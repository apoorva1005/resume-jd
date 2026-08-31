# Build sequence

Order to create files when building Resume–JD Matcher from scratch, with one line on what each file does.

---

## Phase 1 — Skeleton & config

| # | File | What it does |
|---|------|----------------|
| 1 | `.env.example` | Template for Mongo URI, Chroma settings, JWT secret, and optional LLM keys |
| 2 | `.env` | Local secrets (not committed); copy from `.env.example` |
| 3 | `backend/requirements.txt` | Python dependencies for FastAPI, Mongo, Chroma, ML, parsing |
| 4 | `backend/app/__init__.py` | Marks `app` as a package |
| 5 | `backend/app/config.py` | Loads settings from environment into one settings object |
| 6 | `backend/app/db.py` | Async Mongo client, collection handles, and index setup |
| 7 | `backend/app/vectorstore.py` | Chroma client, resume/JD embedding collections, async query wrappers |
| 8 | `backend/app/schemas.py` | Pydantic request/response models shared by the API |

---

## Phase 2 — Auth

| # | File | What it does |
|---|------|----------------|
| 9 | `backend/app/auth.py` | bcrypt password hashing, JWT issue/verify, `current_user` dependency |
| 10 | `backend/app/routers/__init__.py` | Marks `routers` as a package |
| 11 | `backend/app/routers/auth_routes.py` | Signup and login endpoints |
| 12 | `backend/app/main.py` | FastAPI entrypoint: lifespan, CORS, mounts routers, `/health` |

---

## Phase 3 — ML services (pure logic, no HTTP)

| # | File | What it does |
|---|------|----------------|
| 13 | `backend/app/services/__init__.py` | Marks `services` as a package |
| 14 | `backend/app/services/parsing.py` | Turns PDF/DOCX into plain text and rough resume sections |
| 15 | `backend/app/services/embeddings.py` | Bi-encoder embed, cosine similarity, and cross-encoder score |
| 16 | `backend/app/services/features.py` | Keyword overlap, years-of-experience, and education signals |
| 17 | `backend/app/services/scoring.py` | Weighted sum of the five match features |
| 18 | `backend/app/services/vector_search.py` | Chroma metadata builder and `where`-clause builder |
| 19 | `backend/app/services/retrieval.py` | Chunks the resume and picks top-k chunks for the explanation |
| 20 | `backend/app/services/explain.py` | LLM explanation (Groq → Gemini) or keyword-gap template fallback |

---

## Phase 4 — API routes

| # | File | What it does |
|---|------|----------------|
| 21 | `backend/app/routers/documents.py` | Upload/list resumes and JDs; parse, embed, store in Mongo + Chroma |
| 22 | `backend/app/routers/match_routes.py` | Score a resume–JD pair and return the explanation |
| 23 | `backend/app/routers/search.py` | Vector similarity search with metadata filtering, both directions |

---

## Phase 5 — Frontend

| # | File | What it does |
|---|------|----------------|
| 24 | `frontend/index.html` | Page markup: auth, upload, match, search, history |
| 25 | `frontend/style.css` | Layout and styling (no CSS framework) |
| 26 | `frontend/api.js` | Fetch wrapper to `/api`, JWT in localStorage |
| 27 | `frontend/app.js` | UI logic: tabs, upload, match, search, history |

---

## Phase 6 — Scripts, tests, deploy

| # | File | What it does |
|---|------|----------------|
| 28 | `backend/scripts/dev_server.py` | Serves the frontend and proxies `/api` for non-Docker local run |
| 29 | `backend/scripts/create_vector_index.py` | Creates the optional Atlas Vector Search index |
| 30 | `backend/scripts/reindex_chroma.py` | Rebuilds the Chroma index from Mongo (backfill and repair) |
| 31 | `backend/tests/test_api.py` | API tests: auth, isolation, upload → match, vector search |
| 32 | `frontend/test_render.js` | Checks HTML escaping and markdown render helpers |
| 33 | `backend/Dockerfile` | Builds the backend image (includes ML models) |
| 34 | `frontend/Dockerfile` | Builds the nginx image that serves static files |
| 35 | `frontend/nginx.conf` | Serves the SPA and proxies `/api` to the backend |
| 36 | `docker-compose.yml` | Runs frontend + backend + chroma together |
| 37 | `README.md` | How it works, how to run, design notes |

---

## Dependency flow

```
config → db, vectorstore → schemas
              ↓
            auth → auth_routes → main
              ↓
 parsing → embeddings → features → scoring → vector_search → retrieval → explain
              ↓
     documents → match_routes → search
              ↓
     index.html → style.css → api.js → app.js
              ↓
     scripts → tests → Docker → README
```
