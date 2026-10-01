from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.base import Base
from ..models import (
    Change,
    ChangeStatus,
    EntityCurrent,
    EntityType,
    IngestionEvent,
    SourceChannel,
)
from ..schemas.ingest import NormalizedEntity

_MAX_ACQUIRE_ATTEMPTS = 4


async def record_rejection(
    session: AsyncSession,
    *,
    event_id: str,
    source: SourceChannel,
    event_type: str | None,
    reason: str,
) -> None:
    await session.execute(
        insert(IngestionEvent)
        .values(
            event_id=event_id,
            source=source,
            event_type=event_type,
            entity_keys=[],
            status=ChangeStatus.REJECTED,
            changes_count=0,
            error=reason[:2000],
            completed_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
    )
    await session.commit()


async def claim_event(
    session: AsyncSession,
    *,
    event_id: str,
    source: SourceChannel,
    event_type: str | None,
    entity_keys: Sequence[str],
) -> tuple[IngestionEvent, bool]:
    return await _upsert_locked(
        session=session,
        model=IngestionEvent,
        key_columns=["event_id"],
        values={
            "event_id": event_id,
            "source": source,
            "event_type": event_type,
            "entity_keys": list(entity_keys),
            "status": ChangeStatus.APPLIED,
            "changes_count": 0,
        },
    )


async def lock_entity(
    session: AsyncSession,
    entity_type: EntityType,
    entity_key: str,
    product_sku: str,
) -> tuple[EntityCurrent, bool]:
    return await _upsert_locked(
        session=session,
        model=EntityCurrent,
        key_columns=["entity_type", "entity_key"],
        values={
            "entity_type": entity_type,
            "entity_key": entity_key,
            "product_sku": product_sku,
            "state": {},
            "state_hash": "",
            "version": 0,
        },
    )


async def touch_entity(
    session: AsyncSession,
    entity_type: EntityType,
    entity_key: str,
) -> None:
    await session.execute(
        update(EntityCurrent)
        .where(
            EntityCurrent.entity_type == entity_type,
            EntityCurrent.entity_key == entity_key,
        )
        .values(last_seen_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def update_entity(
    session: AsyncSession,
    row: EntityCurrent,
    next_version: int,
    entity: NormalizedEntity,
) -> None:
    row.version = next_version
    row.state = entity.state
    row.state_hash = entity.state_hash
    row.product_sku = entity.product_sku
    if entity.source_updated_at is not None:
        row.source_updated_at = entity.source_updated_at

    session.add(row)
    await session.commit()


async def append_change(
    session: AsyncSession,
    *,
    entity: NormalizedEntity,
    version: int,
    diff: Sequence[Mapping[str, Any]],
    source: SourceChannel,
    source_event_id: str | None,
    source_updated_at: datetime | None,
) -> Change:
    row = Change(
        entity_type=entity.entity_type,
        entity_key=entity.entity_key,
        product_sku=entity.product_sku,
        version=version,
        state=entity.state,
        state_hash=entity.state_hash,
        diff=[dict(entry) for entry in diff],
        source=source,
        source_event_id=source_event_id,
        source_updated_at=source_updated_at,
    )
    session.add(row)
    await session.flush()
    return row


async def complete_event(
    session: AsyncSession,
    *,
    event_id: str,
    status: ChangeStatus,
    changes_count: int,
) -> None:
    await session.execute(
        update(IngestionEvent)
        .where(IngestionEvent.event_id == event_id)
        .values(
            status=status,
            changes_count=changes_count,
            completed_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def _upsert_locked[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    key_columns: Sequence[str],
    values: dict[str, Any],
) -> tuple[ModelT, bool]:
    lookup = [getattr(model, name) == values[name] for name in key_columns]

    for _ in range(_MAX_ACQUIRE_ATTEMPTS):
        inserted = (
            await session.execute(
                insert(model)
                .values(**values)
                .on_conflict_do_nothing(index_elements=list(key_columns))
                .returning(getattr(model, key_columns[0]))
            )
        ).scalar_one_or_none()

        row = (await session.execute(select(model).where(*lookup).with_for_update())).scalar_one_or_none()

        if row is not None:
            return row, inserted is not None

    key = ", ".join(f"{name}={values[name]!r}" for name in key_columns)
    raise RuntimeError(f"Could not lock {model.__tablename__} row for {key} after {_MAX_ACQUIRE_ATTEMPTS} attempts")
