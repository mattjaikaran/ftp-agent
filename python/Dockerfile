# Stage 1: Python backend
FROM ghcr.io/astral-sh/uv:0.6-python3.12-bookworm-slim AS backend
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY ftp_agent/ ftp_agent/
COPY prompts/ prompts/
COPY config/ config/
RUN uv sync --frozen --no-dev

# Stage 2: Frontend build
FROM oven/bun:1 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

# Stage 3: Runtime
FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 1000 --create-home agent
WORKDIR /app

COPY --from=backend /app/.venv /app/.venv
COPY --from=backend /app/ftp_agent /app/ftp_agent
COPY --from=backend /app/prompts /app/prompts
COPY --from=backend /app/config /app/config
COPY --from=frontend /app/dist /app/static

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN mkdir /data && chown agent:agent /data
VOLUME /data

USER agent
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/api/health').raise_for_status()"

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "ftp_agent", "serve", "--host", "0.0.0.0"]
