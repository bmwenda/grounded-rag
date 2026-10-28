# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM python:3.12-slim-bookworm AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_CONCURRENT_DOWNLOADS=4 UV_HTTP_TIMEOUT=120
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --no-install-package opencv-python \
    --python /usr/local/bin/python3.12 \
    && uv pip install --python /opt/venv/bin/python --no-deps opencv-python-headless==4.11.0.86

FROM dependencies AS test-dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-groups --no-install-project --no-install-package opencv-python \
    --python /usr/local/bin/python3.12 \
    && uv pip install --python /opt/venv/bin/python --no-deps opencv-python-headless==4.11.0.86

FROM dependencies AS application
COPY README.md ./
COPY src/ src/
COPY scripts/ scripts/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-package opencv-python \
    --python /usr/local/bin/python3.12 \
    && uv pip install --python /opt/venv/bin/python --no-deps opencv-python-headless==4.11.0.86

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=application /opt/venv /opt/venv
COPY src/ src/
COPY scripts/ scripts/
COPY migrations/ migrations/
COPY alembic.ini ./
ENV PATH="/opt/venv/bin:${PATH}" PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PORT=10000
RUN useradd --system --create-home --home-dir /home/app app \
    && mkdir -p /app/sources /home/app/.cache \
        /opt/venv/lib/python3.12/site-packages/rapidocr/models \
    && chown app:app /app/sources /home/app /home/app/.cache \
        /opt/venv/lib/python3.12/site-packages/rapidocr/models
ENV HOME=/home/app HF_HOME=/home/app/.cache/huggingface \
    XDG_CACHE_HOME=/home/app/.cache
USER app
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port \"${PORT:-10000}\""]

FROM runtime AS test
COPY --from=test-dependencies /opt/venv /opt/venv
COPY tests/ tests/
CMD ["pytest", "-q"]

# The default target is the web app for Git-backed Dockerfile builds.
FROM runtime AS web
