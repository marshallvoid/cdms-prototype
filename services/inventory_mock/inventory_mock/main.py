import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .routers import admin, products
from .services import FaultInjector, InventoryStore, get_settings
from .settings import Settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await configure_app(app, settings)
        app.state.mutator = None

        if settings.mutation_interval > 0:
            app.state.mutator = asyncio.create_task(_mutation_loop(app, settings))

        logger.info(
            "inventory mock ready: %d products, %d inventory rows",
            app.state.store.stats()["products"],
            app.state.store.stats()["inventory_rows"],
        )

        try:
            yield
        finally:
            if app.state.mutator is not None:
                app.state.mutator.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await app.state.mutator

    app = FastAPI(
        title="Mock VietFul Inventory Service",
        version="1.0.0",
        description="Partial emulation of the VietFul v1 Products API.",
        lifespan=lifespan,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", ())[1:])
        return JSONResponse(
            status_code=400,
            content={
                "code": "VALIDATION_ERROR",
                "errorMessage": f"{location or 'body'}: {first.get('msg', 'invalid request')}",
            },
        )

    @app.get("/health", include_in_schema=False)
    async def health(request: Request) -> dict[str, object]:
        return {"status": "ok", **request.app.state.store.stats()}

    app.include_router(products.router)
    app.include_router(admin.router)

    return app


async def configure_app(app: FastAPI, settings: Settings) -> None:
    app.state.store = InventoryStore(
        product_count=settings.product_count,
        seed=settings.seed,
        warehouse_codes=tuple(settings.warehouse_codes),
        condition_codes=tuple(settings.condition_codes),
        unit_codes=tuple(settings.unit_codes),
    )
    app.state.faults = FaultInjector(settings)


async def _mutation_loop(app: FastAPI, settings: Settings) -> None:
    while True:
        try:
            await asyncio.sleep(settings.mutation_interval)
            changed = await app.state.store.mutate(1)
            if changed["products"] or changed["inventories"]:
                logger.info("background mutation: %s", changed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("background mutation failed")


app = create_app()
