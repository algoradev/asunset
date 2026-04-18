# Product API container. Build context is the consumer repo root, so
# the image can COPY both vendor/asunset/packages/asunset_core AND
# vendor/asunset/apps/api alongside the product code.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl wget \
    && rm -rf /var/lib/apt/lists/*

# Vendored asunset packages — install the two Python packages the
# product depends on, in order. Each editable install satisfies the
# next step's dep resolution without reaching PyPI.
COPY vendor/asunset/packages/asunset_core /packages/asunset_core
COPY vendor/asunset/apps/api /packages/asunset_api
RUN pip install --upgrade pip \
 && pip install -e /packages/asunset_core \
 && pip install -e /packages/asunset_api

# Product code.
COPY apps/product-api/pyproject.toml apps/product-api/README.md ./
COPY apps/product-api/src/ ./src/
COPY apps/product-api/alembic.ini ./
COPY apps/product-api/alembic/ ./alembic/
COPY apps/product-api/entrypoint.sh ./
RUN chmod +x entrypoint.sh \
 && pip install -e .

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "product_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
