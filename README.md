# Resume–JD Matcher

Upload a resume and a job description, get a match score with a written
explanation of the strengths and gaps.

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
[ embed ]         all-MiniLM-L6-v2, 384-dim
     |            stored twice, on purpose: MongoDB is the durable copy,
     |            Chroma is the queryable index (see "Why both databases")
     |
     +--> cosine similarity ..................... a cheap baseline
     +--> cross-encoder (ms-marco-MiniLM-L-6-v2)  reads both together
     +--> keyword overlap, years, education ..... regex features
     |
     v
[ score ]         weighted sum of the five signals
     |
     v
[ explain ]       top-4 resume chunks by relevance -> LLM, grounded only
     |            in those chunks
```

Alongside that pair-scoring path, Chroma answers the *many-candidates*
question:

```
JD (or free text)
     |
     v
[ embed ]  the query vector -- a stored one if you picked an existing JD
     |
     v
[ Chroma ] metadata pre-filter (user_id, years, degree, source, date)
     |     then cosine kNN over whatever survived the filter
     v
ranked resumes, each with its similarity and metadata
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

### Why both databases

MongoDB and Chroma hold the same 384-dim vectors, which looks like duplication
until you ask which one you'd rebuild from. Mongo owns the document — the file
in GridFS, the parsed text, the sections, the vector, the audit trail of
matches. Chroma owns nothing: every vector in it is derived from a
Mongo document, which is what makes `scripts/reindex_chroma.py` possible and
what makes it safe to delete `chroma_data/` or lose the container's volume.

What Chroma buys is the query Mongo can't answer cheaply. Scoring one chosen
resume against one chosen JD needs no index — it's a single dot product, and
that's the `/matches` path. Ranking *every* resume against a JD is a kNN search
with a filter, and doing it in Python means loading every vector into the
application on each request. Chroma keeps an HNSW index and applies the
metadata filter *before* traversing it, so `k=5` means the best five of the
documents that passed the filter, not five results trimmed down afterwards.

**Metadata is derived at index time from the same functions the scorer uses.**
`years_experience` and `degree_rank` come from `extract_years` and
`highest_degree` in `features.py`, so a filter and a score can't disagree about
how many years a resume claims. Two timestamps are stored — `created_at` for
display and `created_ts` as an epoch int — because Chroma compares numbers, not
dates, so `$gte` on a date filter needs the integer form.

**`user_id` is in the metadata filter, not applied afterwards.** Same argument
as the Mongo queries below: `build_where()` in `services/vector_search.py` is
the only way a `where` clause gets constructed, and it always starts from the
owner condition. Another tenant's resume is never a candidate for the
nearest-neighbour search in the first place. `test_search_is_isolated_between_users`
pins this — without the filter, a vector search would happily return every
tenant's closest matches.

**Chroma being down degrades rather than breaks.** Uploads still write to Mongo
and return `indexed: false`; direct matching still works; only the `/search`
endpoints return 503. `reindex_chroma.py` backfills whatever was missed. That
tradeoff is deliberate — losing an upload over an index hiccup would be worse
than a temporarily stale index.

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

### 3. Vector store

Nothing to set up for Docker — `docker compose` runs a `chroma` service and
points the backend at it with `CHROMA_MODE=http`.

Running the backend outside Docker, the default `CHROMA_MODE=persistent` keeps
the index in a local `chroma_data/` folder with no server involved. The
collections are created on first use.

If you already have documents in Mongo from before Chroma was added, backfill
the index:

```bash
cd backend && python scripts/reindex_chroma.py
```

Chroma is a derived index, so this is also the repair command — run it after
losing `chroma_data/`, or when an upload came back `indexed: false`. Re-running
it is safe; upserts are keyed by the Mongo `_id`.

MongoDB Atlas also has its own vector search, and `scripts/create_vector_index.py`
still sets that index up. It is genuinely optional now that Chroma serves the
search path — see the note under *Design decisions*.

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

---

## Design decisions

**Tenant isolation is enforced in application code.** MongoDB has no row-level
security, so every query against `resumes`, `jds`, and `matches`
carries `user_id` in the filter — not as a check after the fetch. The
distinction matters: a document belonging to someone else simply doesn't exist
as far as the query is concerned, so there's no code path that reads a
document and forgets to compare owners. Postgres RLS would push this into the
database and make it impossible to forget; here it's a discipline, which is
why `test_tenant_isolation` exists to enforce it.

The Atlas vector index also declares `user_id` as a filter field, and the
Chroma `where` clause is built by a single function that always includes the
owner condition — so both vector paths pre-filter by owner rather than filtering
after retrieval.

**`pymongo.AsyncMongoClient`, not `motor`.** Motor was deprecated in 2025 and
reached end of life in May 2026. The async client now ships inside pymongo
with the same API, so this is one fewer dependency.

**Chroma runs synchronously, so every call goes through `asyncio.to_thread`.**
The chromadb client has no async API in local or persistent mode. Calling it
directly from an async endpoint would block the event loop for the duration of
the query, which on a single worker means blocking every other request too.
`vectorstore._run` is the one place that wrapping happens.

**Atlas Vector Search is now the redundant one.** `create_vector_index.py`
predates Chroma and still works, but nothing in the app queries `$vectorSearch`
any more — Chroma serves the search path in every mode, including local
development, where Atlas would need a network round-trip to a cloud cluster.
The script is kept because the index costs nothing to have and the Atlas path is
worth showing; if you'd rather not maintain two, deleting it and its README step
would break nothing.

**The default weights are a prior, not a fitted result.** `DEFAULT_WEIGHTS` in
`scoring.py` is a hand-picked starting point, with the
cross-encoder weighted highest because it's the strongest single signal.

---

## Vector search API

```
POST /search/resumes    rank your resumes against a JD (or free text)
POST /search/jds        rank your JDs against a resume (or free text)
GET  /search/stats      how many of your documents are in each collection
```

Both search endpoints take the same body. Give `query_id` to reuse an existing
document's stored vector, or `query_text` to embed something ad hoc:

```json
{
  "query_id": "65f...",
  "k": 5,
  "filters": {
    "min_years": 5,
    "min_degree_rank": 2,
    "source": "file",
    "created_after": "2026-01-01T00:00:00Z",
    "has_skills_section": true,
    "must_contain": "Kubernetes"
  }
}
```

Every filter is optional; omitted keys aren't applied. `min_degree_rank` uses
the `DEGREE_RANK` scale from `features.py` (1 bachelors, 2 masters, 3
doctorate). `must_contain` is the one that isn't metadata — it's a
`where_document` substring filter, so it can insist on a literal term the
embedding may have generalised away. The response echoes back the conditions
Chroma actually applied:

```json
{
  "hits": [{"id": "...", "similarity": 0.71, "years_experience": 6, "...": "..."}],
  "count": 1,
  "filters_applied": ["user_id eq 65f...", "years_experience gte 5"],
  "query_kind": "jd",
  "searched_kind": "resume"
}
```

`/health` reports the vector store's state and stays 200 when Chroma is down —
`vector_store.connected` is where that shows up, so the container isn't taken
out of rotation over an optional index.

---

## Tests

```bash
cd backend && python -m pytest tests -q      # 18 tests, ~40s
cd frontend && node test_render.js           # 14 checks, instant
```

The backend tests use real ML models, a faked MongoDB, and a real in-memory
Chroma (`chroma_mode = "memory"`). Chroma is *not* mocked — ranking and metadata
filtering are actually executed, which is the only way a test can catch a
`where` clause that silently matches nothing.

They cover auth rejection, duplicate signup, tenant isolation across
Mongo collections, the full upload → match flow, upload validation,
and for the vector path: that the relevant resume out-ranks an unrelated one,
that ad-hoc text queries work, that each metadata filter excludes before
ranking, that `must_contain` beats a closer vector match, that search runs in
both directions, and that one user's search never reaches another user's
vectors.

The frontend test extracts the two pure render helpers straight out of
`app.js` (by name, not by copy) and runs them against a real API explanation,
plus hostile input to confirm the escaping holds.

---

## Frontend notes

No framework, no build step, no `node_modules` — four static files served by
nginx. For a UI this size, a bundler would be more moving parts than app.

The **Search** tab is the Chroma-facing one: pick a JD (or type free text), set
the metadata filters, and get every resume back ranked by similarity with the
applied filter conditions listed underneath. Blank filter inputs are left out of
the request body entirely rather than sent as `null`, so the server applies only
what it receives.

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

---

## Known limitations

- **Section splitting is header-keyword matching.** It handles a standard
  single-column resume and gives up gracefully on two-column layouts —
  everything lands in `other`, and matching still works since the full text is
  embedded regardless.
- **No OCR.** A scanned-image PDF yields no text and is rejected with a message
  saying so.
- **Years-of-experience extraction is a regex** for "N years". It misses
  experience implied by date ranges ("2019–2025"). Chroma's `years_experience`
  metadata inherits this, so a `min_years` filter can exclude a resume that
  never spells the number out.
- **Chroma metadata is a snapshot from upload time.** Nothing recomputes it if
  `features.py` changes how years or degrees are extracted — run
  `reindex_chroma.py --all` after touching those functions, or filters will
  disagree with scores.
- **Free-tier hosting sleeps.** The first request after an idle period pays a
  cold start while the models load.

---

## Layout

```
backend/
  app/
    config.py       settings from environment
    db.py           Mongo client, collection handles, index setup
    vectorstore.py  Chroma client, the two embedding collections, async wrappers
    auth.py         bcrypt + JWT + the current_user dependency
    schemas.py      request/response models
    main.py         app entry; warms models on startup
    routers/        auth, documents, matches, search
    services/
      parsing.py       file -> text -> sections
      embeddings.py    embed / cosine / cross_encode
      features.py      keyword overlap, years, education
      scoring.py       weighted sum of the five signals
      retrieval.py     chunking + top-k selection for RAG
      vector_search.py Chroma metadata + where-clause builders
      explain.py       Groq -> Gemini -> template fallback
  scripts/
    create_vector_index.py
    reindex_chroma.py  rebuilds the Chroma index from Mongo
    dev_server.py     serves the frontend + proxies /api, for non-Docker dev
  tests/test_api.py
frontend/
  index.html        markup
  style.css         plain CSS, no framework
  api.js            fetch wrapper, token handling
  app.js            UI logic: tabs, upload, match, search, history
  nginx.conf        static serving + /api proxy
  test_render.js    node checks for the pure render helpers
```
