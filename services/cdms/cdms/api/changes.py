from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Change, EntityCurrent, EntityType, IngestionEvent, SourceChannel
from ..repositories import queries
from ..schemas.api import ChangeOut, ChangePage, EntityCurrentOut
from .deps import get_session

router = APIRouter(prefix="/api/v1", tags=["read"])


@router.get("/stats")
async def stats(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    return {
        "changes": await queries.count_rows(session, Change),
        "ingestion_events": await queries.count_rows(session, IngestionEvent),
        "current_entities": await queries.count_rows(session, EntityCurrent),
    }


@router.get("/changes", response_model=ChangePage)
async def list_changes(
    session: Annotated[AsyncSession, Depends(get_session)],
    sku: str | None = None,
    entity_type: EntityType | None = None,
    entity_key: str | None = None,
    source: SourceChannel | None = None,
    since: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> ChangePage:
    rows, total = await queries.list_changes(
        session,
        sku=sku,
        entity_type=entity_type,
        entity_key=entity_key,
        source=source,
        since=since,
        limit=limit,
        offset=offset,
    )

    return ChangePage(
        total=total,
        limit=limit,
        offset=offset,
        items=[ChangeOut.model_validate(row) for row in rows],
    )


@router.get("/products/current", response_model=list[EntityCurrentOut])
async def list_current_products(
    session: Annotated[AsyncSession, Depends(get_session)],
    sku: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> list[EntityCurrentOut]:
    return await _list_current(session, EntityType.PRODUCT, sku, limit)


@router.get("/inventories/current", response_model=list[EntityCurrentOut])
async def list_current_inventories(
    session: Annotated[AsyncSession, Depends(get_session)],
    sku: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> list[EntityCurrentOut]:
    return await _list_current(session, EntityType.INVENTORY, sku, limit)


async def _list_current(
    session: AsyncSession,
    entity_type: EntityType,
    sku: str | None,
    limit: int,
) -> list[EntityCurrentOut]:
    rows = await queries.list_current(
        session,
        entity_type=entity_type,
        sku=sku,
        limit=limit,
    )
    return [EntityCurrentOut.model_validate(row) for row in rows]
