from typing import cast

from fastapi import Request

from .faults import FaultInjector
from .settings import Settings, get_settings
from .store import InventoryStore


def get_store(request: Request) -> InventoryStore:
    return cast("InventoryStore", request.app.state.store)


def get_faults(request: Request) -> FaultInjector:
    return cast("FaultInjector", request.app.state.faults)


def split_csv(value: str | None) -> list[str] | None:
    if value is None or not value.strip():
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


__all__ = [
    "FaultInjector",
    "InventoryStore",
    "Settings",
    "get_faults",
    "get_settings",
    "get_store",
    "split_csv",
]
