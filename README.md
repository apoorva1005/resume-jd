# Resume–JD Matcher

Upload a resume and a job description → get a match score and a written
explanation of strengths and gaps.

```
resume + JD
   → parse (PDF/DOCX/TXT)
   → embed (MiniLM) + cross-encoder + keyword/years/education features
   → weighted score
   → LLM explanation (or keyword-gap template if no API key)
```

## Run

1. Copy `.env.example` → `.env`, set `MONGODB_URI` and `JWT_SECRET`.
2. Optional: set `GROQ_API_KEY` or `GEMINI_API_KEY` for written explanations.
3. `docker compose up --build`
4. Open http://localhost:8080

## Layout

```
backend/app/
  main.py, config.py, db.py, auth.py, schemas.py
  routers/     auth, documents, matches
  services/    parsing, embeddings, features, scoring, retrieval, explain
frontend/      index.html, style.css, api.js, app.js
```
