from uuid import UUID

from pydantic import BaseModel


class SweepCounters(BaseModel):
    pages: int = 0
    entities_seen: int = 0
    created: int = 0
    changed: int = 0
    unchanged: int = 0
    stale: int = 0
    invalid: int = 0

    def merge(self, counts: dict[str, int]) -> None:
        for name in ("created", "changed", "unchanged", "stale"):
            setattr(self, name, getattr(self, name) + counts.get(name, 0))


class SweepResult(BaseModel):
    run_id: UUID
    status: str
    counters: SweepCounters
    error: str | None = None
