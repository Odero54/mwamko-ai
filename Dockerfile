# This Dockerfile uses multi-stage builds to create optimized Docker images for
# different purposes: building the application, running tests and, servbing the
# app.

FROM docker.io/library/python:3.12-slim-bookworm AS base

SHELL ["/usr/bin/bash", "-euo", "pipefail", "-c"]

WORKDIR /app

# Ref: https://docs.astral.sh/uv/guides/integration/docker/
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/

# =========================================================================== #

FROM base AS deps

COPY ./pyproject.toml ./uv.lock ./

RUN uv sync --locked --no-install-project

# =========================================================================== #

FROM deps AS ci

COPY ./ ./

RUN <<EOF
    uv sync --locked --offline
    uv run ruff check --select I
    uv run ruff format --check
    uv run mypy ./src/
EOF

CMD ["uv", "run", "pytest", "./src/"]

# =========================================================================== #

FROM deps AS build

COPY ./ ./

RUN uv sync --locked --offline --no-default-groups --no-editable --compile-bytecode

# =========================================================================== #

FROM base AS app

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

COPY --from=build /app/.venv/ ./.venv/

EXPOSE ${PORT}

CMD ["uv", "run", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "mwamko_ai.main:app"]