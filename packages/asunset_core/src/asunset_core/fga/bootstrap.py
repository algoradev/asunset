"""Idempotent OpenFGA bootstrap.

On every API start:
  1. Ensure a store named `settings.openfga_store_name` exists (create if not).
  2. Write the caller's authorization model — pinning the returned
     model_id is how we roll forward (FGA models are append-only).
  3. Return (store_id, model_id) for the rest of the app to use.

The caller (asunset_api, or a consumer product) passes the model it
wants pinned. asunset_core has no knowledge of any specific model shape;
that's product territory.

Implementation uses httpx directly because the SDK's high-level client
needs store_id up front — exactly what this function is resolving.
"""

from __future__ import annotations

from typing import Any

import httpx

from asunset_core.config import CoreSettings as Settings
from asunset_core.logging import get_logger

log = get_logger(__name__)


async def bootstrap_openfga(
    settings: Settings, authorization_model: dict[str, Any]
) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {settings.openfga_api_key}"}
    async with httpx.AsyncClient(
        base_url=settings.openfga_api_url, timeout=10.0, headers=headers
    ) as client:
        store_id = await _ensure_store(client, settings.openfga_store_name)
        model_id = await _write_model(client, store_id, authorization_model)

    log.info(
        "fga.bootstrap.ok",
        store_id=store_id,
        model_id=model_id,
        store_name=settings.openfga_store_name,
    )
    return store_id, model_id


async def _ensure_store(client: httpx.AsyncClient, name: str) -> str:
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


async def _write_model(
    client: httpx.AsyncClient, store_id: str, model: dict[str, Any]
) -> str:
    resp = await client.post(
        f"/stores/{store_id}/authorization-models",
        json=model,
    )
    resp.raise_for_status()
    return resp.json()["authorization_model_id"]
