FROM python:3.13.14-slim-trixie

ARG POETRY_VERSION=2.4.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_REQUESTS_TIMEOUT=120 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /workspace

RUN addgroup --system fashion && adduser --system --ingroup fashion fashion \
    && pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock ./
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --no-root

COPY --chown=fashion:fashion app ./app
COPY --chown=fashion:fashion alembic.ini ./
COPY --chown=fashion:fashion migrations ./migrations
COPY --chown=fashion:fashion tests ./tests

USER fashion

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]
