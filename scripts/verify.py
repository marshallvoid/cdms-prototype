from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "cdms"))

from cdms.models import Change, ChangeStatus, EntityCurrent, IngestionEvent  # type: ignore
from stack_client import DATABASE_URL, rule

CONNECT_TIMEOUT_SECONDS = 30.0
APPLIED = ChangeStatus.APPLIED.value


def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or DATABASE_URL
    scheme, separator, rest = url.partition("://")
    if separator and "+" not in scheme:
        return f"postgresql+asyncpg://{rest}"
    return url


async def wait_for_database(engine: AsyncEngine) -> None:
    deadline = time.monotonic() + CONNECT_TIMEOUT_SECONDS
    while True:
        try:
            async with engine.connect():
                return
        except OperationalError:
            if time.monotonic() >= deadline:
                shown = make_url(database_url()).render_as_string(hide_password=True)
                print(f"\n  !! cannot reach the database at {shown}", file=sys.stderr)
                print("     start postgres with: make up", file=sys.stderr)
                raise SystemExit(1) from None
            await asyncio.sleep(2.0)


async def _count(session: AsyncSession, statement: Any) -> int:
    return int((await session.execute(statement)).scalar_one())


def _per_entity() -> Any:
    return (
        select(
            Change.entity_type.label("entity_type"),
            Change.entity_key.label("entity_key"),
            func.count().label("rows"),
            func.max(Change.version).label("top"),
        )
        .group_by(Change.entity_type, Change.entity_key)
        .subquery()
    )


def _same_entity(history: Any) -> Any:
    return and_(
        history.c.entity_type == EntityCurrent.entity_type,
        history.c.entity_key == EntityCurrent.entity_key,
    )


async def check_one_row_per_version(session: AsyncSession) -> int:
    repeated = (
        select(Change.entity_key)
        .group_by(Change.entity_type, Change.entity_key, Change.version)
        .having(func.count() > 1)
        .subquery()
    )
    return await _count(session, select(func.count()).select_from(repeated))


async def check_one_row_per_event(session: AsyncSession) -> int:
    repeated = (
        select(IngestionEvent.event_id)
        .group_by(IngestionEvent.event_id)
        .having(func.count() > 1)
        .subquery()
    )
    return await _count(session, select(func.count()).select_from(repeated))


async def check_no_version_gaps(session: AsyncSession) -> int:
    history = _per_entity()
    gapped = (
        select(history.c.entity_key).where(history.c.rows != history.c.top).subquery()
    )
    return await _count(session, select(func.count()).select_from(gapped))


async def check_current_matches_history(session: AsyncSession) -> int:
    history = _per_entity()
    drifted = (
        select(EntityCurrent.entity_key)
        .outerjoin(history, _same_entity(history))
        .where(EntityCurrent.version != func.coalesce(history.c.top, 0))
        .subquery()
    )
    untracked = (
        select(history.c.entity_key)
        .outerjoin(EntityCurrent, _same_entity(history))
        .where(EntityCurrent.entity_key.is_(None))
        .subquery()
    )
    drifted_count = await _count(session, select(func.count()).select_from(drifted))
    untracked_count = await _count(session, select(func.count()).select_from(untracked))
    return drifted_count + untracked_count


async def check_ledger_matches_rows(session: AsyncSession) -> tuple[int, int]:
    ledger = await _count(
        session,
        select(func.coalesce(func.sum(IngestionEvent.changes_count), 0)).where(
            IngestionEvent.status == APPLIED
        ),
    )
    rows = await _count(session, select(func.count()).select_from(Change))
    return ledger, rows


async def check_non_applied_wrote_nothing(session: AsyncSession) -> int:
    statement = (
        select(func.count())
        .select_from(Change)
        .join(IngestionEvent, IngestionEvent.event_id == Change.source_event_id)
        .where(IngestionEvent.status != APPLIED)
    )
    return await _count(session, statement)


async def collect(session: AsyncSession) -> list[tuple[str, str, bool]]:
    ledger, rows = await check_ledger_matches_rows(session)
    dupe_versions = await check_one_row_per_version(session)
    dupe_events = await check_one_row_per_event(session)
    gaps = await check_no_version_gaps(session)
    drift = await check_current_matches_history(session)
    no_ops = await check_non_applied_wrote_nothing(session)

    return [
        ("1  duplicate (entity, version) rows", str(dupe_versions), dupe_versions == 0),
        ("2  duplicate event_id rows", str(dupe_events), dupe_events == 0),
        ("3  entities with a version gap", str(gaps), gaps == 0),
        ("4  entities diverging from history", str(drift), drift == 0),
        (
            "5  ledger changes_count vs change rows",
            f"{ledger} = {rows}",
            ledger == rows,
        ),
        ("6  change rows from a non-applied event", str(no_ops), no_ops == 0),
    ]


async def verify() -> int:
    engine = create_async_engine(database_url())
    await wait_for_database(engine)
    try:
        async with AsyncSession(engine) as session:
            lines = await collect(session)
            totals = [
                (
                    "changes",
                    await _count(session, select(func.count()).select_from(Change)),
                ),
                (
                    "events",
                    await _count(
                        session, select(func.count()).select_from(IngestionEvent)
                    ),
                ),
                (
                    "entities",
                    await _count(
                        session, select(func.count()).select_from(EntityCurrent)
                    ),
                ),
            ]
    finally:
        await engine.dispose()

    rule("Checks")
    for label, value, _passed in lines:
        print(f"  {label:<40}: {value}")

    print(f"\n  totals: {', '.join(f'{value} {name}' for name, value in totals)}")

    rule("Verdict")
    if all(passed for _, _, passed in lines):
        print("  every entity version was written once, and no replay wrote anything")
        return 0
    print("  FAIL: exactly-once is broken")
    return 1


def main() -> int:
    print("CDMS exactly-once verification")
    print("=============================")
    print(
        "one row per delivery, one row per entity version, nothing written by a replay"
    )
    return asyncio.run(verify())


if __name__ == "__main__":
    raise SystemExit(main())
