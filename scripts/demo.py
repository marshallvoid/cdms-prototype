from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stack_client import (
    cdms,
    changes,
    emit_event,
    inventory,
    poll_now,
    rule,
    stats,
    wait_for_stack,
)

RUN = uuid.uuid4().hex[:8]
DEMO_SKU = f"DEMO-{RUN}"


def show_poll(result: dict) -> None:
    print(
        f"  status={result['status']} pages={result['pages']} seen={result['entities_seen']} "
        f"created={result['created']} changed={result['changed']} "
        f"unchanged={result['unchanged']} stale={result['stale']}"
    )
    if result.get("error"):
        print(f"  error: {result['error']}")


def step_1_inventory_is_seen(api, mock) -> None:
    rule("1. First sweep — everything in the source is new")
    show_poll(poll_now(api))
    state = mock.get("/_admin/state").json()
    print(f"  the mock holds {state['products']} products and {state['inventory_rows']} stock rows")
    print(f"  the CDMS now holds {stats(api)['current_entities']} entities")


def step_2_nothing_moves(api) -> None:
    rule("2. Second sweep — the source has not changed, so nothing is written")
    before = stats(api)["changes"]
    show_poll(poll_now(api))
    after = stats(api)["changes"]
    print(f"  changes before={before} after={after}  (a naive poller would have doubled this)")


def step_3_only_real_drift(api, mock) -> None:
    rule("3. Change a few upstream rows, then sweep again")
    mutated = mock.post("/_admin/mutate", json={"count": 5}).json()
    moved = len(mutated["products"]) + len(mutated["inventories"])
    before = stats(api)["changes"]
    result = poll_now(api)
    after = stats(api)["changes"]
    show_poll(result)
    print(f"  the mock moved {moved} rows; the CDMS stored {after - before} changes")


def step_4_duplicates_are_free(api) -> None:
    rule("4. The same webhook delivered three times")
    event_id = f"demo-{RUN}-dup"
    answers = [emit_event(api, event_id, DEMO_SKU, 100) for _ in range(3)]
    for attempt, answer in enumerate(answers, start=1):
        print(
            f"  delivery {attempt}: status={answer['status']} changes={answer['changes']} "
            f"version={answer.get('version')}"
        )
    print("  one delivery did the work; the retries answered 'duplicate' and wrote nothing")


def step_5_stale_events_do_not_rewind(api) -> None:
    rule("5. A late event whose source timestamp is older than what is stored")
    fresh = emit_event(api, f"demo-{RUN}-fresh", DEMO_SKU, 90)
    print(f"  applied version {fresh['version']} with physicalQty=90")
    payload = emit_event(api, f"demo-{RUN}-stale", DEMO_SKU, 5, stamp="2020-01-01T00:00:00+00:00")
    print(
        f"  the older event: status={payload['status']} changes={payload['changes']} "
        f"(physicalQty=5 was rejected as stale, not applied)"
    )
    current = api.get("/api/v1/inventories/current", params={"sku": DEMO_SKU}).json()
    print(f"  stored state is still physicalQty={current[0]['state']['physicalQty']}")


def step_6_a_to_b_to_a(api) -> None:
    rule("6. A -> B -> A is three transitions, not two")
    for index, qty in enumerate((70, 80, 70), start=1):
        answer = emit_event(api, f"demo-{RUN}-aba-{index}", DEMO_SKU, qty)
        print(f"  physicalQty={qty}: status={answer['status']} version={answer['version']}")


def step_7_feed(api) -> None:
    rule("7. The change feed for the demo SKU")
    page = changes(api, sku=DEMO_SKU, limit=20)
    print(f"  {page['total']} changes recorded")
    for item in page["items"]:
        moved = ", ".join(entry["field"] for entry in item["diff"]) or "(creation)"
        print(f"  v{item['version']:<3} {item['source']:<8} {item['entity_key']:<28} {moved}")


def step_8_summary(api) -> None:
    rule("8. Totals")
    totals = stats(api)
    print(
        f"  current entities: {totals['current_entities']}\n"
        f"  stored changes:   {totals['changes']}\n"
        f"  ingestion events: {totals['ingestion_events']}  (replays included)"
    )
    print('\n  Next: python scripts/chaos.py')


def main() -> int:
    print("CDMS demonstration")
    print("=================")
    wait_for_stack()

    with cdms() as api, inventory() as mock:
        step_1_inventory_is_seen(api, mock)
        step_2_nothing_moves(api)
        step_3_only_real_drift(api, mock)
        step_4_duplicates_are_free(api)
        step_5_stale_events_do_not_rewind(api)
        step_6_a_to_b_to_a(api)
        step_7_feed(api)
        step_8_summary(api)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
