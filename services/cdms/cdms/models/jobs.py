import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class PollRun(Base):
    __tablename__ = "poll_runs"
    __table_args__ = (Index("poll_runs_started_idx", "started_at"),)

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False, default="schedule")
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entities_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
