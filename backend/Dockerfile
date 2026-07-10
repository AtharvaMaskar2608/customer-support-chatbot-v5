# Backend API image — FastAPI served by uvicorn on :8000.
# Build from the repo root:  docker build -f backend/Dockerfile -t <repo>:backend .
FROM python:3.12-slim

# uv for fast, lockfile-reproducible installs (copied from the official uv image).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 1) Install dependencies only — cached until pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Copy the app and install the project itself.
COPY backend ./backend
RUN uv sync --frozen --no-dev

# Run the venv's binaries directly (no `uv run` wrapper needed at runtime).
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
# Secrets (DATABASE_URL, ANTHROPIC_API_KEY, ...) are provided at runtime via --env-file,
# never baked into the image. DATABASE_URL must be reachable from wherever this runs.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
