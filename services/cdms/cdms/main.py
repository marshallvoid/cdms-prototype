import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import admin, changes, health, webhooks
from .config import Settings, get_settings
from .db.base import Base
from .db.session import Database
from .services.inventory_client import InventoryClient
from .workers.poller import InventoryPoller
from .workers.scheduler import PollerScheduler

logger = logging.getLogger(__name__)


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    database: Database = app.state.database
    await database.wait_until_ready()

    if settings.auto_create_schema:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("schema created from metadata (auto_create_schema is on)")

    scheduler = app.state.scheduler
    scheduler.start()

    try:
        yield
    finally:
        await scheduler.stop()
        await app.state.inventory_client.aclose()
        await database.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Change Data Management Service",
        version="1.0.0",
        description="Change Data Management Service",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = Database(settings)
    app.state.inventory_client = InventoryClient(
        settings.inventory_base_url,
        timeout=settings.inventory_timeout_seconds,
        retries=settings.inventory_retries,
        backoff=settings.inventory_retry_backoff,
    )
    app.state.poller = InventoryPoller(settings, app.state.database, app.state.inventory_client)
    app.state.scheduler = PollerScheduler(app.state.poller, settings)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        location = ".".join(str(part) for part in first.get("loc", ())[1:])
        return JSONResponse(
            status_code=400,
            content={
                "code": "VALIDATION_ERROR",
                "errorMessage": f"{location or 'body'}: {first.get('msg', 'invalid request')}",
            },
        )

    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(changes.router)
    app.include_router(admin.router)

    return app


app = create_app()
