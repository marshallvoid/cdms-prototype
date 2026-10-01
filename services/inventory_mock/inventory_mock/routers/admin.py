import uuid
from datetime import UTC, datetime
from typing import Literal, cast

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..faults import FaultInjector, FaultState
from ..services import get_faults, get_settings, get_store
from ..settings import Settings
from ..store import InventoryStore, inventory_payload_of

router = APIRouter(prefix="/_admin", tags=["test-control"], include_in_schema=False)

EventType = Literal[
    "PRODUCT_CREATED",
    "PRODUCT_UPDATED",
    "PRODUCT_DEACTIVATED",
    "INVENTORY_UPDATED",
]


class MutateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=1000)
    seed: int | None = None


class FaultRequest(BaseModel):
    mode: Literal["error", "timeout", "malformed", "rate_limit"] | None = None
    scope: Literal["products", "inventories", "*"] = "*"
    count: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(default=0, ge=0, le=60_000)


class EmitRequest(BaseModel):
    event_type: EventType = "INVENTORY_UPDATED"
    sku: str | None = None
    event_id: str | None = None
    repeats: int = Field(default=1, ge=1, le=200)
    payload: dict[str, object] | None = None
    url: str | None = None


@router.post("/mutate")
async def mutate(body: MutateRequest, store: InventoryStore = Depends(get_store)) -> dict[str, object]:
    return cast("dict[str, object]", await store.mutate(body.count, seed=body.seed))


@router.post("/reset")
async def reset(store: InventoryStore = Depends(get_store)) -> dict[str, int]:
    return await store.reset()


@router.get("/state")
async def get_state(
    store: InventoryStore = Depends(get_store),
    faults: FaultInjector = Depends(get_faults),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return {
        **store.stats(),
        "fault": _describe_state(faults.current()),
        "webhookUrl": settings.cdms_webhook_url,
    }


@router.get("/faults")
async def read_faults(faults: FaultInjector = Depends(get_faults)) -> dict[str, object]:
    return _describe_state(faults.current())


@router.post("/faults")
async def set_faults(body: FaultRequest, faults: FaultInjector = Depends(get_faults)) -> dict[str, object]:
    state = await faults.set(mode=body.mode, scope=body.scope, count=body.count, latency_ms=body.latency_ms)
    return _describe_state(state)


@router.delete("/faults")
async def clear_faults(faults: FaultInjector = Depends(get_faults)) -> dict[str, object]:
    return _describe_state(await faults.clear())


@router.get("/inventory/{sku}")
async def get_inventory(sku: str, store: InventoryStore = Depends(get_store)) -> list[dict[str, object]]:
    rows = await store.list_inventories(skus=[sku])
    return [inventory_payload_of(row) for row in rows]


@router.post("/emit-webhook")
async def emit_webhook(
    body: EmitRequest,
    store: InventoryStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    event_id = body.event_id or str(uuid.uuid4())
    data = body.payload or await _resolve_payload(body, store)
    event = {
        "eventId": event_id,
        "eventType": body.event_type,
        "occurredAt": datetime.now(UTC).isoformat(),
        "source": "vietful",
        "data": data,
    }
    url = body.url or settings.cdms_webhook_url

    deliveries: list[dict[str, object]] = []
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        for attempt in range(1, body.repeats + 1):
            try:
                response = await client.post(url, json=event)
            except httpx.HTTPError as exc:
                deliveries.append({"attempt": attempt, "error": type(exc).__name__})
                continue

            try:
                body_res = response.json()
            except ValueError:
                body_res = response.text

            deliveries.append(
                {
                    "attempt": attempt,
                    "status": response.status_code,
                    "body": body_res,
                }
            )

    return {"eventId": event_id, "url": url, "event": event, "deliveries": deliveries}


def _describe_state(state: FaultState) -> dict[str, object]:
    return {
        "mode": state.mode,
        "scope": state.scope,
        "remaining": state.remaining,
        "latencyMs": state.latency_ms,
    }


async def _resolve_payload(body: EmitRequest, store: InventoryStore) -> dict[str, object]:
    if body.event_type == "INVENTORY_UPDATED":
        keys = await store.all_inventory_keys()
        sku = body.sku or (keys[0][0] if keys else "SKU-000001")
        record = await store.inventory_payload(sku)

        if record is not None:
            return record

        for key in keys:
            record = await store.inventory_payload(key[0])
            if record is not None:
                return record

        return {"sku": sku}

    sku = body.sku or "SKU-000001"
    return await store.product_payload(sku) or {"sku": sku}
