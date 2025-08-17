# Use slim Python image with Debian base
FROM python:3.12-slim

# ---- Environment (unchanged) ----
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    POETRY_VIRTUALENVS_CREATE=false \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 \
    REMBG_MODEL=u2netp \
    REMBG_MAX_CONCURRENCY=1 \
    BG_MAX_SIDE=800

# ---- System deps (unchanged; this layer will be cached) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git wget libssl-dev libffi-dev libbz2-dev \
    liblzma-dev libsqlite3-dev zlib1g-dev libxml2-dev libxmlsec1-dev \
    graphviz graphviz-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ---- Build-time toggle (added *after* apt so cache is preserved) ----
ARG ENABLE_BG_REMOVAL=0
ENV ENABLE_BG_REMOVAL=${ENABLE_BG_REMOVAL}

# NEW: allow/deny writes to caches (1 = write, 0 = read-only)
ARG CACHE_WRITE=0
ENV CACHE_WRITE=${CACHE_WRITE}

# ---- Python deps (same as before, but without rembg) ----
RUN pip install --upgrade pip && pip install poetry gunicorn pillow

# ---- Conditionally install rembg/onnxruntime (new, isolated step) ----
RUN if [ "$ENABLE_BG_REMOVAL" = "1" ]; then \
      pip install rembg onnxruntime && \
      python3 -c "from rembg.session_factory import new_session; new_session('u2netp')" ; \
    fi

# ---- App code (unchanged) ----
WORKDIR /pelagica
COPY . .

# Install project deps (unchanged)
RUN poetry install --no-interaction --no-ansi

# ---- Run with one worker (unchanged) ----
#CMD ["poetry", "run", "gunicorn", "app:server", "-b", "0.0.0.0:8050", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--timeout", "120", "--max-requests", "200", "--max-requests-jitter", "50"]

#CMD ["poetry", "run", "gunicorn", "app:server","-b", "0.0.0.0:8050","--preload", "--workers", "1","--worker-class", "gthread","--threads", "4","--timeout", "300", "--max-requests", "0"]        


# optional: ensure the cache dirs exist (safe no-ops if they already do)
RUN mkdir -p /pelagica/image_cache /pelagica/text_cache /pelagica/data/processed

# Start: if CACHE_WRITE=0, make caches read-only, then run gunicorn
CMD ["sh","-c", "\
  if [ \"${CACHE_WRITE:-1}\" != \"1\" ]; then \
    chmod -R a-w /pelagica/image_cache /pelagica/text_cache || true; \
  fi; \
  exec poetry run gunicorn app:server -b 0.0.0.0:8050 \
    --workers 1 --worker-class gthread --threads 4 --timeout 300 --preload \
    --max-requests 200 --max-requests-jitter 50 \
"]
