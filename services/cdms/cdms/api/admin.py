from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PollRun
from ..schemas.api import PollRunOut, PollRunTriggered
from .deps import InventoryPoller, get_poller, get_session

router = APIRouter(prefix="/api/v1", tags=["operations"])


@router.get("/poll-runs", response_model=list[PollRunOut])
async def list_poll_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(20, ge=1, le=200),
) -> list[PollRunOut]:
    statement = select(PollRun).order_by(PollRun.started_at.desc()).limit(limit)
    rows = (await session.execute(statement)).scalars()

    return [PollRunOut.model_validate(row) for row in rows]


@router.post("/admin/poll/run", response_model=PollRunTriggered)
async def trigger_poll(
    poller: Annotated[InventoryPoller, Depends(get_poller)],
) -> PollRunTriggered:
    result = await poller.run_once(triggered_by="manual")
    return PollRunTriggered(
        run_id=str(result.run_id),
        status=result.status,
        pages=result.counters.pages,
        entities_seen=result.counters.entities_seen,
        created=result.counters.created,
        changed=result.counters.changed,
        unchanged=result.counters.unchanged,
        stale=result.counters.stale,
        error=result.error,
    )
