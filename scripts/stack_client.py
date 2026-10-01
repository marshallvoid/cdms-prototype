from __future__ import annotations

import os
import sys
import time
from typing import Any

import httpx

CDMS_URL = os.environ.get("CDMS_URL", "http://localhost:8001").rstrip("/")
MOCK_URL = os.environ.get("MOCK_URL", "http://localhost:8000").rstrip("/")
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql://cdms:cdms@localhost:5432/cdms"),
)


def _fail(message: str) -> None:
    print(f"\n  !! {message}", file=sys.stderr)
    raise SystemExit(1)


def wait_for_stack(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    pending = {"cdms": f"{CDMS_URL}/api/v1/ready", "inventory": f"{MOCK_URL}/health"}
    while pending and time.monotonic() < deadline:
        for name, url in list(pending.items()):
            try:
                if httpx.get(url, timeout=2.0).status_code == 200:
                    del pending[name]
            except httpx.HTTPError:
                pass
        if pending:
            time.sleep(1.0)
    if pending:
        _fail(
            "the stack is not up: "
            + ", ".join(f"{name} ({url}) did not answer" for name, url in pending.items())
            + "\n     start it with: docker compose up -d --build"
        )


def cdms() -> httpx.Client:
    # A manual sweep is synchronous and walks the whole source page by page, so
    # it outlasts any per-request budget that suits the read APIs.
    return httpx.Client(base_url=CDMS_URL, timeout=300.0)


def inventory() -> httpx.Client:
    return httpx.Client(base_url=MOCK_URL, timeout=30.0)


def poll_now(client: httpx.Client) -> dict[str, Any]:
    response = client.post("/api/v1/admin/poll/run")
    response.raise_for_status()
    return response.json()


def changes(client: httpx.Client, **params: Any) -> dict[str, Any]:
    response = client.get("/api/v1/changes", params={"limit": 20, **params})
    response.raise_for_status()
    return response.json()


def stats(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/api/v1/stats")
    response.raise_for_status()
    return response.json()


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def emit_event(
    client: httpx.Client,
    event_id: str,
    sku: str,
    physical: int,
    *,
    stamp: str | None = None,
) -> dict[str, Any]:
    stamp = stamp or time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    payload = {
        "eventId": event_id,
        "eventType": "INVENTORY_UPDATED",
        "occurredAt": stamp,
        "source": "vietful",
        "data": {
            "sku": sku,
            "partnerSKU": sku,
            "warehouseCode": "KQ7",
            "unitCode": "CAI",
            "conditionTypeCode": "NEW",
            "physicalQty": physical,
            "availableQty": physical,
            "pendingInQty": 0,
            "pendingOutQty": 0,
            "freezeQty": 0,
            "inTransitQty": 0,
            "lastUpdatedDate": stamp,
        },
    }
    response = client.post("/api/v1/webhooks/inventory", json=payload)
    response.raise_for_status()
    return response.json()
