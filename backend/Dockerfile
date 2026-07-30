FROM python:3.13.14-slim-trixie AS production-builder

ARG POETRY_VERSION=2.4.1

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_REQUESTS_TIMEOUT=120 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /workspace

RUN python -m venv /opt/venv \
    && /usr/local/bin/pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --only main --no-root


FROM production-builder AS development-builder

RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --no-root


FROM python:3.13.14-slim-trixie AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/fashion \
    XDG_CACHE_HOME=/home/fashion/.cache \
    PATH=/opt/venv/bin:$PATH

RUN addgroup --system fashion \
    && adduser --system --ingroup fashion --home /home/fashion fashion \
    && mkdir -p /home/fashion/.cache \
    && chown -R fashion:fashion /home/fashion

WORKDIR /workspace


FROM runtime-base AS production

COPY --from=production-builder /opt/venv /opt/venv
COPY --chown=fashion:fashion app ./app
COPY --chown=fashion:fashion alembic.ini ./
COPY --chown=fashion:fashion migrations ./migrations

USER fashion

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM runtime-base AS development

COPY --from=development-builder /opt/venv /opt/venv
COPY --chown=fashion:fashion app ./app
COPY --chown=fashion:fashion alembic.ini ./
COPY --chown=fashion:fashion migrations ./migrations
COPY --chown=fashion:fashion tests ./tests

USER fashion

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]
