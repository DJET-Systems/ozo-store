# syntax=docker/dockerfile:1.7

FROM python:3.14-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    PATH="/app/.venv/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /bin/uv

RUN groupadd -g 10001 djet && \
    useradd -u 10001 -g 10001 -m -s /usr/sbin/nologin djet

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY manage.py ./
COPY djet_store ./djet_store
COPY config ./config
COPY apps ./apps
COPY samples ./samples

RUN uv sync --frozen --no-dev --no-editable && \
    mkdir -p /app/staticfiles /app/media && \
    DJET_ENV=dev DJANGO_SETTINGS_MODULE=config.settings.storefront python manage.py collectstatic --noinput && \
    chown -R djet:djet /app

USER djet

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2"]
