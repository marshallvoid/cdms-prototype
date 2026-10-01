from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models import EntityType, SourceChannel


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: EntityType
    entity_key: str
    product_sku: str
    version: int
    state_hash: str
    state: dict[str, Any]
    diff: list[dict[str, Any]]
    source: SourceChannel
    source_event_id: str | None = None
    source_updated_at: datetime | None = None
    observed_at: datetime


class ChangePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ChangeOut]


class EntityCurrentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: EntityType
    entity_key: str
    product_sku: str
    version: int
    state_hash: str
    state: dict[str, Any]
    source_updated_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime


class PollRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    status: str
    triggered_by: str
    pages: int
    entities_seen: int
    created: int
    changed: int
    unchanged: int
    stale: int
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class PollRunTriggered(BaseModel):
    run_id: str
    status: str
    pages: int
    entities_seen: int
    created: int
    changed: int
    unchanged: int
    stale: int
    error: str | None = None
