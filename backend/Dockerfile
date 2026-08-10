# Python 3.11 rather than 3.13: torch and sentence-transformers have the
# widest wheel coverage here, so builds don't fall back to compiling.
FROM python:3.11-slim

WORKDIR /app

# curl for the healthcheck below; nothing else is needed at runtime since we
# install CPU-only wheels.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install torch from the CPU index first. The default PyPI wheel bundles CUDA
# and is ~2.5GB, which won't fit in a free-tier image.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Bake the models into the image so the first request isn't a 200MB download.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
