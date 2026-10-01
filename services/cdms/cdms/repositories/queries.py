from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Change, EntityCurrent, EntityType, SourceChannel


async def count_rows(
    session: AsyncSession,
    model: type,
    filters: list[Any] | None = None,
) -> int:
    query = select(func.count()).select_from(model)
    if filters:
        query = query.where(*filters)
    return (await session.execute(query)).scalar_one()


async def list_changes(
    session: AsyncSession,
    *,
    sku: str | None = None,
    entity_type: EntityType | None = None,
    entity_key: str | None = None,
    source: SourceChannel | None = None,
    since: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[Sequence[Change], int]:
    filters: list[Any] = []
    if sku:
        filters.append(Change.product_sku == sku)

    if entity_type is not None:
        filters.append(Change.entity_type == entity_type)

    if entity_key:
        filters.append(Change.entity_key == entity_key)

    if source is not None:
        filters.append(Change.source == source)

    if since is not None:
        filters.append(Change.observed_at >= since)

    total = await count_rows(session=session, model=Change, filters=filters)
    rows = (
        await session.execute(
            select(Change)
            .where(*filters)
            .order_by(Change.observed_at.desc(), Change.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows), total


async def list_current(
    session: AsyncSession,
    *,
    entity_type: EntityType,
    sku: str | None,
    limit: int,
) -> Sequence[EntityCurrent]:
    filters: list[Any] = [EntityCurrent.entity_type == entity_type]
    if sku:
        filters.append(EntityCurrent.product_sku == sku)

    rows = (await session.execute(select(EntityCurrent).where(*filters).limit(limit))).scalars()
    return list(rows)
