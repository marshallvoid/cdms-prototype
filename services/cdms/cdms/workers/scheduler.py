import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..config import Settings
from .poller import InventoryPoller

logger = logging.getLogger(__name__)

JOB_ID = "inventory-poll"


class PollerScheduler:
    def __init__(self, poller: InventoryPoller, settings: Settings) -> None:
        self._poller = poller
        self._settings = settings
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        if not self._settings.poll_enabled:
            logger.info("scheduled polling is disabled")
            return

        self._scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(seconds=self._settings.poll_interval_seconds),
            id=JOB_ID,
            name="inventory poll",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=self._settings.poll_interval_seconds,
            next_run_time=datetime.now(UTC) + timedelta(seconds=self._settings.poll_startup_delay_seconds),
        )
        self._scheduler.start()

        logger.info(
            "polling %s every %ds",
            self._settings.inventory_base_url,
            self._settings.poll_interval_seconds,
        )

    async def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        logger.info("poller scheduler stopped")

    async def _tick(self) -> None:
        try:
            result = await self._poller.run_once(triggered_by="schedule")
        except Exception:
            logger.exception("scheduled poll raised")
            return

        if result.status not in ("completed", "skipped"):
            logger.warning("scheduled poll %s: %s", result.run_id, result.error)
