from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from .enums import (
    CHANGE_STATUS_ENUM,
    ENTITY_TYPE_ENUM,
    SOURCE_CHANNEL_ENUM,
    ChangeStatus,
    EntityType,
    SourceChannel,
)


class EntityCurrent(Base):
    __tablename__ = "entity_current"
    __table_args__ = (Index("entity_current_sku_idx", "product_sku"),)

    entity_type: Mapped[EntityType] = mapped_column(ENTITY_TYPE_ENUM, primary_key=True)
    entity_key: Mapped[str] = mapped_column(Text, primary_key=True)

    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    product_sku: Mapped[str] = mapped_column(Text, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Change(Base):
    __tablename__ = "changes"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_key",
            "version",
            name="uq_changes_entity_version",
        ),
        Index("changes_sku_observed_idx", "product_sku", "observed_at"),
        Index(
            "changes_source_event_idx",
            "source_event_id",
            postgresql_where="source_event_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    entity_type: Mapped[EntityType] = mapped_column(ENTITY_TYPE_ENUM, nullable=False)
    entity_key: Mapped[str] = mapped_column(Text, nullable=False)

    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    diff: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    product_sku: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[SourceChannel] = mapped_column(SOURCE_CHANNEL_ENUM, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(Text)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"
    __table_args__ = (Index("ingestion_source_received_idx", "source", "received_at"),)

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[SourceChannel] = mapped_column(SOURCE_CHANNEL_ENUM, nullable=False)
    event_type: Mapped[str | None] = mapped_column(Text)
    entity_keys: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    status: Mapped[ChangeStatus] = mapped_column(CHANGE_STATUS_ENUM, nullable=False)
    changes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
