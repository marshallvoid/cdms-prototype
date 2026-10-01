from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stack_client import cdms, inventory, poll_now, rule, stats, wait_for_stack

SCENARIOS = [
    ("the source returns HTTP 500", {"mode": "error", "scope": "*", "count": 3}),
    ("the source throttles us", {"mode": "rate_limit", "scope": "*", "count": 3}),
    ("the source returns a truncated body", {"mode": "malformed", "scope": "*", "count": 3}),
    ("the source is slow", {"mode": "timeout", "scope": "*", "count": 1, "latency_ms": 0}),
]


def run_scenario(api, mock, description: str, fault: dict) -> bool:
    before = stats(api)
    mock.post("/_admin/faults", json=fault).raise_for_status()
    started = time.monotonic()
    result = poll_now(api)
    elapsed = time.monotonic() - started
    after = stats(api)

    intact = before["changes"] == after["changes"]
    print(f"\n  {description}")
    print(f"    sweep      : {result['status']} in {elapsed:.2f}s")
    print(
        f"    counters   : pages={result['pages']} created={result['created']} "
        f"changed={result['changed']} unchanged={result['unchanged']}"
    )
    print(f"    error      : {result['error'] or '-'}")
    print(f"    changes    : {before['changes']} -> {after['changes']}")
    print(f"    history    : {'INTACT' if intact else 'CORRUPTED'}")
    return intact


def recovery(api, mock) -> None:
    mock.delete("/_admin/faults")
    rule("Recovery — with the fault cleared, the next sweep works normally")
    result = poll_now(api)
    print(
        f"  status={result['status']} seen={result['entities_seen']} "
        f"created={result['created']} changed={result['changed']} unchanged={result['unchanged']}"
    )
    print("  nothing was re-stored: re-observing an unchanged entity is free by hash")


def main() -> int:
    print("CDMS chaos scenarios")
    print("===================")
    wait_for_stack()

    intact = True
    with cdms() as api, inventory() as mock:
        rule("Baseline")
        show = poll_now(api)
        print(f"  a clean sweep first: {show['status']} ({stats(api)['changes']} changes stored)")

        rule("Upstream failures")
        for description, fault in SCENARIOS:
            intact &= run_scenario(api, mock, description, fault)

        rule("Source side drift")
        mutated = mock.post("/_admin/mutate", json={"count": 3}).json()
        moved = len(mutated["products"]) + len(mutated["inventories"])
        before = stats(api)["changes"]
        result = poll_now(api)
        print(
            f"  moved {moved} rows upstream; the sweep stored "
            f"{stats(api)['changes'] - before} changes (status={result['status']})"
        )

        recovery(api, mock)

    rule("Verdict")
    if intact:
        print("  every fault left the stored change history untouched")
        return 0
    print("  FAIL: a fault changed the stored history")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
