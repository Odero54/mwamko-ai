FROM docker.io/library/python:3.12-slim-bookworm AS base

SHELL ["/usr/bin/bash", "-euo", "pipefail", "-c"]

WORKDIR /app

# Install uv globally
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH"

# ========================== #
# Dependencies stage
# ========================== #
FROM base AS deps

COPY ./pyproject.toml ./uv.lock ./
RUN uv sync --locked --no-install-project

# ========================== #
# Build stage
# ========================== #
FROM deps AS build

COPY ./src ./src
COPY ./pyproject.toml ./uv.lock ./
RUN uv sync --locked --offline --no-default-groups --no-editable --compile-bytecode

# ========================== #
# Final app image
# ========================== #
FROM base AS app

ENV PORT=8000

# Copy virtual environment
COPY --from=build /app/.venv/ ./.venv/

# Copy source
COPY ./src ./src

EXPOSE 8000

# IMPORTANT: use correct module path!
CMD ["uv", "run", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "src.mwamko_ai.main:app"]