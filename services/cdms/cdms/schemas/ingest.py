from dataclasses import field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from ..models import ChangeStatus, EntityType, SourceChannel

Outcome = Literal["created", "changed", "unchanged", "stale"]


class NormalizedEntity(BaseModel):
    entity_type: EntityType
    entity_key: str
    product_sku: str
    state: dict[str, Any]
    state_hash: str
    source_updated_at: datetime | None = None


class IngestRequest(BaseModel):
    source: SourceChannel
    event_id: str
    entities: tuple[NormalizedEntity, ...]
    event_type: str | None = None


class EntityOutcome(BaseModel):
    entity_type: EntityType
    entity_key: str
    outcome: Outcome
    version: int


class IngestResult(BaseModel):
    event_id: str
    status: ChangeStatus
    changes: int
    outcomes: tuple[EntityOutcome, ...] = field(default=())

    @property
    def is_duplicate(self) -> bool:
        return self.status is ChangeStatus.DUPLICATE


class Verdict(BaseModel):
    kind: Outcome
    diff: tuple[dict[str, Any], ...]
