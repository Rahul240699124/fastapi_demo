# Dockerfile - recipe for a container IMAGE that runs this app anywhere Docker runs.
#
# Build & run on its own:   docker build -t fastapi-demo .
# Usually you'll use docker-compose.yml instead (app + MySQL together):
#                           docker compose up --build

# 1) Start from an official, small Python image (same version as .python-version).
FROM python:3.14-slim

# 2) Copy the uv binary in from its official image (pinned version = reproducible builds).
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

WORKDIR /app

# UV_COMPILE_BYTECODE: pre-compile .pyc files -> faster container start.
# UV_LINK_MODE=copy: avoids hard-link warnings inside Docker layers.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 3) Install dependencies FIRST, copying only the two files that list them.
#    Docker caches each step: as long as pyproject.toml/uv.lock don't change, this slow
#    step is reused, and editing your code only re-runs the fast steps below.
#    --locked: use exactly the versions in uv.lock.   --no-dev: skip pytest etc.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# 4) Now copy the application code (.dockerignore keeps .venv, .env, media... out).
COPY . .

# Put the virtualenv's executables (fastapi, alembic, ...) on the PATH.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# 5) On start: bring the DB schema up to date, then run the production server.
#    `fastapi run` = production mode (no auto-reload); --host 0.0.0.0 so it's
#    reachable from outside the container.
CMD ["sh", "-c", "alembic upgrade head && fastapi run main.py --host 0.0.0.0 --port 8000"]
