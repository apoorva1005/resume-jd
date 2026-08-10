# Resume–JD Matcher

Upload a resume and a job description, get a match score with a written
explanation of the strengths and gaps, then correct the score if it's wrong.
The corrections train a re-ranker that sits on top of frozen embedding models.

Built as a portfolio project: the goal was a complete pipeline that runs
end to end on free tiers, not a state-of-the-art matcher.

---

## How it works

```
resume + JD
     |
     v
[ parse ]         pdfplumber / docx2txt -> text -> rough section split
     |
     v
[ embed ]         all-MiniLM-L6-v2, 384-dim, stored in MongoDB
     |
     +--> cosine similarity ..................... a cheap baseline
     +--> cross-encoder (ms-marco-MiniLM-L-6-v2)  reads both together
     +--> keyword overlap, years, education ..... regex features
     |
     v
[ score ]         weighted sum, or a trained logistic regression once
     |            enough feedback exists
     v
[ explain ]       top-4 resume chunks by relevance -> LLM, grounded only
     |            in those chunks
     v
[ feedback ]      thumbs up/down or a corrected score
     |
     v
[ retrain ]       scikit-learn on (5 features -> good/bad label)
```

### Why two models

The bi-encoder embeds each document independently, so vectors can be cached and
compared cheaply — but each side is encoded without knowing about the other.
The cross-encoder reads the pair together and can weigh how specific terms line
up, which separates near-misses much better. It can't be cached, so it only
runs on the one pair the user asked about.

Measured on a matching ML job description vs an unrelated nursing one:

| pair | cosine | cross-encoder |
|---|---|---|
| relevant JD | 0.666 | **0.958** |
| irrelevant JD | 0.156 | **0.000** |

Cosine puts a totally unrelated JD at 0.156 rather than near zero — it's
picking up on both documents being "a job-shaped document". The cross-encoder
collapses that to 0.0. That gap is the whole argument for the second stage.

### Why retrain only the ranker

The embedding and cross-encoder models stay frozen; their outputs are two of
five input features to a logistic regression. Fine-tuning a transformer needs
thousands of labels and a GPU. Fitting five coefficients needs a few dozen
labels and a laptop — which is the realistic amount of feedback a project like
this collects.

---

## Running it

### 1. MongoDB Atlas

Create a free M0 cluster, add a database user, and allow network access from
`0.0.0.0/0` (fine for a demo; scope it down for anything real). Copy the
connection string.

### 2. Configure

```bash
cp .env.example .env
```

Fill in `MONGODB_URI` and generate a secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

An LLM key is optional. Without one the app still works — explanations fall
back to a keyword-gap template. Free keys:
[Groq](https://console.groq.com/keys) or
[Google AI Studio](https://aistudio.google.com/apikey).

### 3. Vector search index (optional)

```bash
cd backend && python scripts/create_vector_index.py
```

See the tradeoff note below — the app works without this.

### 4. Run

```bash
docker compose up --build
```

- App: http://localhost:8080
- API docs: http://localhost:8080/api/docs

nginx serves the static frontend and proxies `/api` to the backend, so the
browser only ever talks to one origin. That's why there's no CORS handling in
the JavaScript and no backend hostname baked into it.

The first build downloads ~500MB of models and bakes them into the backend
image, so it takes a few minutes. After that, startup is quick.

<details>
<summary>Running without Docker</summary>

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# in a second terminal -- serves the frontend and proxies /api, the same way
# nginx does in Docker
cd backend && python scripts/dev_server.py
```

Then open http://localhost:8080.
</details>

### 5. Retrain after collecting feedback

```bash
cd backend && python scripts/retrain_ranker.py
```

Writes `models/ranker.joblib`. The API watches the file's mtime and picks up a
new model on the next match, no restart needed. Below 20 labelled examples the
script refuses to train and the API keeps using the weighted sum.

Running it on a schedule was a stretch goal and is not implemented — a cron
entry or a GitHub Actions workflow on a weekly trigger would be the next step.

---

## Design decisions

**Tenant isolation is enforced in application code.** MongoDB has no row-level
security, so every query against `resumes`, `jds`, `matches` and `feedback`
carries `user_id` in the filter — not as a check after the fetch. The
distinction matters: a document belonging to someone else simply doesn't exist
as far as the query is concerned, so there's no code path that reads a
document and forgets to compare owners. Postgres RLS would push this into the
database and make it impossible to forget; here it's a discipline, which is
why `test_tenant_isolation` exists to enforce it.

The Atlas vector index also declares `user_id` as a filter field, so
`$vectorSearch` pre-filters by owner rather than filtering after retrieval.

**`pymongo.AsyncMongoClient`, not `motor`.** Motor was deprecated in 2025 and
reached end of life in May 2026. The async client now ships inside pymongo
with the same API, so this is one fewer dependency.

**Vector search is optional.** Matching a chosen resume against a chosen JD is
a direct comparison — it needs no index at all. The index only matters for
"find the best resume among many", which at this scale (a handful of documents
per user) brute-force cosine in Python handles fine. It's set up because the
project is partly about showing the Atlas Vector Search path, but nothing
breaks without it.

**The default weights are a prior, not a fitted result.** `DEFAULT_WEIGHTS` in
`scoring.py` is a hand-picked starting point for the cold-start case, with the
cross-encoder weighted highest because it's the strongest single signal. They
were not tuned on labelled data — that's what the retraining step is for.

**Feedback is one row per user per match.** Resubmitting updates rather than
appends, so a user can't skew training by clicking the same button repeatedly.

---

## Tests

```bash
cd backend && python -m pytest tests -q      # 8 tests, ~35s
cd frontend && node test_render.js           # 14 checks, instant
```

The backend tests use real ML models and a faked MongoDB. They cover auth
rejection, duplicate signup, tenant isolation across all four collections, the
full upload → match → feedback flow, and upload validation.

The frontend test extracts the two pure render helpers straight out of
`app.js` (by name, not by copy) and runs them against a real API explanation,
plus hostile input to confirm the escaping holds.

---

## Frontend notes

No framework, no build step, no `node_modules` — four static files served by
nginx. For a UI this size, a bundler would be more moving parts than app.

**The one place to be careful is `innerHTML`.** The explanation text comes from
an LLM and document previews come from uploaded files, so both are untrusted.
Everything is escaped through `escapeHtml()` before rendering, and
`renderMarkdown()` applies formatting only *after* escaping — so `<script>`
in an explanation renders as visible text rather than executing. That's what
the hostile-input cases in `test_render.js` pin down.

**Tokens live in `localStorage`.** Simple, and it survives a refresh — but it's
readable by any script on the page, which is exactly why the escaping above
matters. A production app would prefer an httpOnly cookie with CSRF
protection; that's a deliberate scope call, not an oversight.

---

## Evaluation

Not yet done, and the README shouldn't pretend otherwise. The intended
approach:

1. Hand-label ~30 resume/JD pairs as good / borderline / bad fits.
2. Report precision@k and Spearman correlation against the human labels for
   three scorers: cosine alone, cosine + cross-encoder, and the full weighted
   sum.
3. After collecting real feedback, compare the trained ranker against the
   weighted-sum baseline on a held-out split.

The retraining script already prints a cross-validated ROC-AUC, which is the
first half of step 3.

---

## Known limitations

- **Section splitting is header-keyword matching.** It handles a standard
  single-column resume and gives up gracefully on two-column layouts —
  everything lands in `other`, and matching still works since the full text is
  embedded regardless.
- **No OCR.** A scanned-image PDF yields no text and is rejected with a message
  saying so.
- **Years-of-experience extraction is a regex** for "N years". It misses
  experience implied by date ranges ("2019–2025").
- **Free-tier hosting sleeps.** The first request after an idle period pays a
  cold start while the models load.

---

## Layout

```
backend/
  app/
    config.py       settings from environment
    db.py           Mongo client, collection handles, index setup
    auth.py         bcrypt + JWT + the current_user dependency
    schemas.py      request/response models
    main.py         app entry; warms models on startup
    routers/        auth, documents, matches, feedback
    services/
      parsing.py    file -> text -> sections
      embeddings.py embed / cosine / cross_encode
      features.py   keyword overlap, years, education
      scoring.py    weighted sum or trained ranker
      retrieval.py  chunking + top-k selection for RAG
      explain.py    Groq -> Gemini -> template fallback
  scripts/
    create_vector_index.py
    retrain_ranker.py
    dev_server.py     serves the frontend + proxies /api, for non-Docker dev
  tests/test_api.py
frontend/
  index.html        markup
  style.css         plain CSS, no framework
  api.js            fetch wrapper, token handling
  app.js            UI logic: tabs, upload, match, feedback, history
  nginx.conf        static serving + /api proxy
  test_render.js    node checks for the pure render helpers
```
