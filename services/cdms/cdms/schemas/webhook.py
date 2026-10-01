from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import EntityType

EventType = Literal[
    "PRODUCT_CREATED",
    "PRODUCT_UPDATED",
    "PRODUCT_DEACTIVATED",
    "INVENTORY_UPDATED",
]

ENTITY_FOR_EVENT: dict[str, EntityType] = {
    "PRODUCT_CREATED": EntityType.PRODUCT,
    "PRODUCT_UPDATED": EntityType.PRODUCT,
    "PRODUCT_DEACTIVATED": EntityType.PRODUCT,
    "INVENTORY_UPDATED": EntityType.INVENTORY,
}


class WebhookEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    eventId: str = Field(min_length=1, max_length=255)
    eventType: EventType
    occurredAt: datetime | None = None
    source: str = "vietful"
    data: dict[str, Any]

    @property
    def entity_type(self) -> EntityType:
        return ENTITY_FOR_EVENT[self.eventType]


class WebhookResponse(BaseModel):
    eventId: str
    status: str
    changes: int
    entityKey: str | None = None
    entityType: str | None = None
    version: int | None = None
    detail: str | None = None
