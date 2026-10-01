from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from .deps import Database, Settings, get_app_settings, get_database

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    settings: Annotated[Settings, Depends(get_app_settings)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    healthy = await database.ping()
    if not healthy:
        return {"status": "unavailable", "database": "down"}

    return {
        "status": "ready",
        "database": "up",
        "pollIntervalSeconds": settings.poll_interval_seconds,
        "pollEnabled": settings.poll_enabled,
    }


@router.get("/db/ping")
async def db_ping(
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    async with database.engine.connect() as connection:
        result = await connection.execute(text("SELECT version()"))
    return {"version": result.scalar_one()}
