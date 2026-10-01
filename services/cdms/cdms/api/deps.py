from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db.session import Database
from ..services.inventory_client import InventoryClient
from ..workers.poller import InventoryPoller


def get_database(request: Request) -> Database:
    return cast("Database", request.app.state.database)


def get_inventory_client(request: Request) -> InventoryClient:
    return cast("InventoryClient", request.app.state.inventory_client)


def get_app_settings(request: Request) -> Settings:
    return cast("Settings", request.app.state.settings)


def get_poller(request: Request) -> InventoryPoller:
    return cast("InventoryPoller", request.app.state.poller)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database = get_database(request)
    async with database.session() as session:
        yield session


__all__ = [
    "Database",
    "InventoryClient",
    "InventoryPoller",
    "Settings",
    "get_app_settings",
    "get_database",
    "get_inventory_client",
    "get_poller",
    "get_session",
    "get_settings",
]
