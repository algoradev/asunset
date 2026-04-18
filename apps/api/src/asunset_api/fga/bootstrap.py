"""Idempotent OpenFGA bootstrap.

On every API start:
  1. Ensure a store named `settings.openfga_store_name` exists (create if not).
  2. Write the current authorization model (always — models are append-only
     in OpenFGA, and pinning the latest ID is how we roll forward).
  3. Return (store_id, model_id) for the rest of the app to use.

Implementation uses httpx directly because the OpenFGA SDK's higher-level
client requires knowing the store_id up front — which is exactly what this
function is resolving. Using the raw HTTP API keeps the dependency surface
small for a one-shot bootstrap path.
"""

from __future__ import annotations

import httpx

from asunset_api.config import Settings
from asunset_api.fga.model import AUTHORIZATION_MODEL
from asunset_api.logging import get_logger

log = get_logger(__name__)


async def bootstrap_openfga(settings: Settings) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {settings.openfga_api_key}"}
    async with httpx.AsyncClient(
        base_url=settings.openfga_api_url, timeout=10.0, headers=headers
    ) as client:
        store_id = await _ensure_store(client, settings.openfga_store_name)
        model_id = await _write_model(client, store_id)

    log.info(
        "fga.bootstrap.ok",
        store_id=store_id,
        model_id=model_id,
        store_name=settings.openfga_store_name,
    )
    return store_id, model_id


async def _ensure_store(client: httpx.AsyncClient, name: str) -> str:
    # Paginate through stores to find one by name. For a template there will
    # usually be one store total, so a single page is plenty.
    continuation: str | None = None
    while True:
        params = {"continuation_token": continuation} if continuation else {}
        resp = await client.get("/stores", params=params)
        resp.raise_for_status()
        data = resp.json()
        for store in data.get("stores", []):
            if store.get("name") == name:
                return store["id"]
        continuation = data.get("continuation_token")
        if not continuation:
            break

    resp = await client.post("/stores", json={"name": name})
    resp.raise_for_status()
    return resp.json()["id"]


async def _write_model(client: httpx.AsyncClient, store_id: str) -> str:
    resp = await client.post(
        f"/stores/{store_id}/authorization-models",
        json=AUTHORIZATION_MODEL,
    )
    resp.raise_for_status()
    return resp.json()["authorization_model_id"]
