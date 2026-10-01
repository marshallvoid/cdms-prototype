from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PollRun
from ..schemas.exception import NotFoundError
from ..schemas.job import SweepCounters


async def create_poll_run(
    session: AsyncSession,
    *,
    run_id: UUID,
    status: str,
    triggered_by: str,
) -> None:
    poll_run = PollRun(
        run_id=run_id,
        status=status,
        triggered_by=triggered_by,
    )
    session.add(poll_run)
    await session.commit()


async def finish_poll_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    status: str,
    error: str | None,
    counters: SweepCounters,
) -> None:
    statement = select(PollRun).where(PollRun.run_id == run_id)
    poll_run = (await session.execute(statement)).scalar_one_or_none()
    if poll_run is None:
        raise NotFoundError(f"Poll run {run_id} vanished before it could be closed")

    poll_run.status = status
    poll_run.error = error
    poll_run.finished_at = datetime.now(UTC)
    poll_run.pages = counters.pages
    poll_run.entities_seen = counters.entities_seen
    poll_run.created = counters.created
    poll_run.changed = counters.changed
    poll_run.unchanged = counters.unchanged
    poll_run.stale = counters.stale

    session.add(poll_run)
    await session.commit()
