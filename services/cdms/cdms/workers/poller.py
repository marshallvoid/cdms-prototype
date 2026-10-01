import asyncio
import logging
import uuid
from typing import Any

from ..config import Settings
from ..db.session import Database
from ..models import EntityType, SourceChannel
from ..repositories import job as job_repo
from ..schemas.exception import InventoryUnavailable
from ..schemas.ingest import IngestRequest, NormalizedEntity
from ..schemas.job import SweepCounters, SweepResult
from ..services.ingest import ingest
from ..services.inventory_client import InventoryClient
from ..services.normalization import (
    normalise_many,
    normalize_inventory,
    normalize_product,
)

logger = logging.getLogger(__name__)

STREAMS: dict[EntityType, tuple[str, Any]] = {
    EntityType.PRODUCT: ("products", normalize_product),
    EntityType.INVENTORY: ("inventories", normalize_inventory),
}


class InventoryPoller:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        client: InventoryClient,
    ) -> None:
        self._database = database
        self._client = client
        self._settings = settings

        self._page_size = self._settings.poll_page_size
        self._max_pages = self._settings.poll_max_pages
        self._lock = asyncio.Lock()

    async def run_once(self, *, triggered_by: str = "schedule") -> SweepResult:
        if self._lock.locked():
            return SweepResult(
                run_id=uuid.uuid4(),
                status="skipped",
                counters=SweepCounters(),
                error="A sweep is already in progress",
            )

        async with self._lock:
            return await self._sweep(triggered_by=triggered_by)

    async def _sweep(self, *, triggered_by: str) -> SweepResult:
        run_id = uuid.uuid4()
        counters = SweepCounters()
        status = "completed"
        error: str | None = None

        async with self._database.session() as session:
            await job_repo.create_poll_run(
                session=session,
                run_id=run_id,
                status="running",
                triggered_by=triggered_by,
            )

        try:
            for entity_type in (EntityType.PRODUCT, EntityType.INVENTORY):
                await self._sweep_entity(
                    entity_type=entity_type,
                    run_id=run_id,
                    counters=counters,
                )

        except InventoryUnavailable as exc:
            status = "partial" if counters.pages else "failed"
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Poll run %s aborted after %d pages: %s",
                run_id,
                counters.pages,
                error,
            )

        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("Poll run %s failed", run_id)

        try:
            async with self._database.session() as session:
                await job_repo.finish_poll_run(
                    session=session,
                    run_id=run_id,
                    status=status,
                    error=error,
                    counters=counters,
                )
        except Exception:
            logger.exception("poll run %s could not be recorded", run_id)

        return SweepResult(run_id=run_id, status=status, counters=counters, error=error)

    async def _sweep_entity(
        self,
        entity_type: EntityType,
        run_id: uuid.UUID,
        counters: SweepCounters,
    ) -> None:
        stream, normalise = STREAMS[entity_type]
        ignored = self._settings.ignored_for(entity_type.value)
        page_index = 0

        async for page in self._client.iter_entities(
            entity_type=entity_type,
            page_size=self._page_size,
            max_pages=self._max_pages,
        ):
            entities = normalise_many(
                page=page,
                normalise=normalise,
                ignored=ignored,
                counters=counters,
            )
            counters.pages += 1
            counters.entities_seen += len(page)
            counters.merge(
                await self._ingest(
                    run_id=run_id,
                    stream=stream,
                    page_index=page_index,
                    entities=entities,
                )
            )
            page_index += 1

    async def _ingest(
        self,
        run_id: uuid.UUID,
        stream: str,
        page_index: int,
        entities: list[NormalizedEntity],
    ) -> dict[str, int]:
        if not entities:
            return {}

        counts = {"created": 0, "changed": 0, "unchanged": 0, "stale": 0}
        async with self._database.session() as session:
            result = await ingest(
                session=session,
                request=IngestRequest(
                    source=SourceChannel.POLL,
                    event_id=f"poll:{run_id}:{stream}:{page_index}",
                    event_type=f"POLL_{stream.upper()}_PAGE",
                    entities=tuple(entities),
                ),
            )

        for outcome in result.outcomes:
            counts[outcome.outcome] += 1

        return counts
