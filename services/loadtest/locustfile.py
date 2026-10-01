from __future__ import annotations

import os
import random
import time
import uuid
from typing import Any

from locust import HttpUser, between, events, task
from requests import Response

WEBHOOK = "/api/v1/webhooks/inventory"
CHANGES = "/api/v1/changes"
CURRENT = "/api/v1/inventories/current"
POLL_RUN = "/api/v1/admin/poll/run"

SKUS_PER_USER = int(os.environ.get("LOAD_SKUS_PER_USER", "10"))
DUPLICATE_RATE = float(os.environ.get("LOAD_DUPLICATE_RATE", "0.2"))
READ_WEIGHT = int(os.environ.get("LOAD_READ_WEIGHT", "3"))
POLL_WEIGHT = int(os.environ.get("LOAD_POLL_WEIGHT", "0"))
STALE_RATE = float(os.environ.get("LOAD_STALE_RATE", "0.05"))

STATS = {
    "sent": 0,
    "applied": 0,
    "unchanged": 0,
    "duplicate": 0,
    "stale": 0,
    "rejected": 0,
}


@events.quitting.add_listener
def _report(environment, **_kwargs) -> None:
    stats = environment.stats
    total = sum(STATS.values()) or 1

    print("\n--- delivery outcomes " + "-" * 50)
    for name, count in STATS.items():
        print(f"{name:>10}: {count:>8}  ({100 * count / total:5.1f}%)")

    print(f"{'requests':>10}: {stats.total.num_requests:>8}")
    print(f"{'failures':>10}: {stats.total.num_failures:>8}")


class IngestionUser(HttpUser):
    wait_time = between(0.0, float(os.environ.get("LOAD_WAIT_MAX", "0.4")))

    def on_start(self) -> None:
        # Locust's User carries no id of its own and runner.user_count is shared by every
        # user spawned in the same tick, so a prefix taken from it makes several users
        # generate the same event ids and replay each other instead of writing.
        self.prefix = f"LOAD{uuid.uuid4().hex[:8]}"
        self.sequence = 0
        self.recent: list[dict[str, Any]] = []

    def _sku(self) -> str:
        return f"{self.prefix}-{random.randrange(SKUS_PER_USER):04d}"

    def _event(self, *, stale: bool = False) -> dict[str, Any]:
        stamp = (
            "2020-01-01T00:00:00+00:00"
            if stale
            else time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        )
        sku = self._sku()
        physical = random.randrange(1, 5_000)

        return {
            "eventId": f"load:{self.prefix}:{self._next()}",
            "eventType": "INVENTORY_UPDATED",
            "occurredAt": stamp,
            "source": "vietful",
            "data": {
                "sku": sku,
                "partnerSKU": sku,
                "warehouseCode": random.choice(["KQ7", "KV3"]),
                "unitCode": random.choice(["CAI", "BOX"]),
                "conditionTypeCode": random.choice(["NEW", "DAMAGED"]),
                "physicalQty": physical,
                "availableQty": physical,
                "pendingInQty": 0,
                "pendingOutQty": 0,
                "freezeQty": 0,
                "inTransitQty": 0,
                "lastUpdatedDate": stamp,
            },
        }

    def _next(self) -> int:
        self.sequence += 1
        return self.sequence

    def _remember(self, event: dict[str, Any]) -> None:
        self.recent.append(event)
        del self.recent[:-64]

    def _record(self, response: Response) -> None:
        if response.status_code >= 400:
            STATS["rejected"] += 1
            return

        status = response.json().get("status", "unknown")
        STATS[status if status in STATS else "rejected"] += 1

    @task(10)
    def deliver_new_event(self) -> None:
        event = self._event(stale=random.random() < STALE_RATE)

        with self.client.post(
            WEBHOOK,
            json=event,
            name="POST /webhooks/inventory (new)",
            catch_response=True,
        ) as response:
            self._record(response)

        self._remember(event)
        STATS["sent"] += 1

    @task(2)
    def deliver_duplicate(self) -> None:
        if not self.recent:
            return

        with self.client.post(
            WEBHOOK,
            json=random.choice(self.recent),
            name="POST /webhooks/inventory (duplicate)",
            catch_response=True,
        ) as response:
            if (
                response.status_code != 200
                or response.json().get("status") != "duplicate"
            ):
                response.failure(
                    f"a replay was not deduplicated: {response.text[:120]}"
                )
            self._record(response)

        STATS["sent"] += 1

    @task(READ_WEIGHT)
    def read_change_feed(self) -> None:
        self.client.get(
            CHANGES,
            params={
                "sku": self._sku(),
                "limit": random.choice([20, 50, 100]),
            },
            name="GET /changes",
        )

    @task(READ_WEIGHT)
    def read_current_state(self) -> None:
        self.client.get(
            CURRENT, params={"sku": self._sku()}, name="GET /inventories/current"
        )

    @task(POLL_WEIGHT)
    def trigger_poll(self) -> None:
        self.client.post(POLL_RUN, name="POST /admin/poll/run")
