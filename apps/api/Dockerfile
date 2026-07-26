# Multi-stage: `base` is the shared build, `dev` adds tooling + reload,
# `prod` is the minimized runtime image.
#
# Build context is the MONOREPO ROOT (see compose.yml), not apps/api/ —
# we need access to packages/asunset_core which is outside the app tree.

# ---------- base ----------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
      wget \
    && rm -rf /var/lib/apt/lists/*

# asunset-core is the shared platform library. Installed first so
# asunset-api's `asunset-core` dep sees it already satisfied and pip
# doesn't try to reach PyPI for it.
COPY packages/asunset_core /packages/asunset_core

COPY apps/api/pyproject.toml apps/api/README.md ./
COPY apps/api/src/ ./src/
COPY apps/api/alembic.ini ./
COPY apps/api/alembic/ ./alembic/
COPY apps/api/features.yaml ./
COPY apps/api/entrypoint.sh ./
RUN chmod +x entrypoint.sh

RUN pip install --upgrade pip \
 && pip install -e /packages/asunset_core \
 && pip install -e .

# ---------- dev ----------
FROM base AS dev

RUN pip install -e ".[dev]"

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "asunset_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------- prod ----------
FROM python:3.12-slim AS prod

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r asunset && useradd -r -g asunset asunset

COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin /usr/local/bin
COPY --from=base /packages/asunset_core /packages/asunset_core
COPY --from=base /app/src /app/src
COPY --from=base /app/alembic.ini /app/
COPY --from=base /app/alembic /app/alembic
COPY --from=base /app/features.yaml /app/
COPY --from=base /app/entrypoint.sh /app/
RUN chown -R asunset:asunset /app /packages/asunset_core

USER asunset
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "asunset_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
