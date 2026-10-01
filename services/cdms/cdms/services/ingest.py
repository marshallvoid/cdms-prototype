import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ChangeStatus
from ..repositories import ingest as ingest_repo
from ..schemas.ingest import (
    EntityOutcome,
    IngestRequest,
    IngestResult,
    NormalizedEntity,
    Verdict,
)
from .normalization import canonical_value

logger = logging.getLogger(__name__)

_RETRYABLE_SQLSTATES = {"40001", "40P01"}
_MAX_ATTEMPTS = 3


async def ingest(
    session: AsyncSession,
    request: IngestRequest,
    max_attempts: int = _MAX_ATTEMPTS,
) -> IngestResult:
    if session.in_transaction():
        raise RuntimeError("ingest() owns its transaction; the session must not already be in one")

    for attempt in range(1, max_attempts + 1):
        try:
            return await _ingest_once(session=session, request=request)
        except OperationalError as exc:
            code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
            if code not in _RETRYABLE_SQLSTATES or attempt == max_attempts:
                raise

            logger.warning(
                "Retrying ingest of %s after %s (attempt %d/%d)",
                request.event_id,
                code,
                attempt,
                max_attempts,
            )
            await asyncio.sleep(0.05 * attempt)

    raise RuntimeError("unreachable: ingest exhausted its attempts without returning or raising")


async def _ingest_once(session: AsyncSession, request: IngestRequest) -> IngestResult:
    event, claimed = await ingest_repo.claim_event(
        session=session,
        event_id=request.event_id,
        source=request.source,
        event_type=request.event_type,
        entity_keys=sorted({entity.entity_key for entity in request.entities}),
    )

    if not claimed:
        return IngestResult(
            event_id=event.event_id,
            status=ChangeStatus.DUPLICATE,
            changes=event.changes_count,
        )

    by_key = {(e.entity_type, e.entity_key): e for e in request.entities}
    outcomes = [
        await _process_entity(session=session, request=request, entity=by_key[pair])
        for pair in sorted(by_key, key=lambda pair: (pair[0].value, pair[1]))
    ]

    if any(outcome.outcome in ("created", "changed") for outcome in outcomes):
        status = ChangeStatus.APPLIED
    elif all(outcome.outcome == "stale" for outcome in outcomes):
        status = ChangeStatus.STALE
    else:
        status = ChangeStatus.UNCHANGED

    changes_count = sum(1 for outcome in outcomes if outcome.outcome in ("created", "changed"))
    await ingest_repo.complete_event(
        session,
        event_id=request.event_id,
        status=status,
        changes_count=changes_count,
    )

    return IngestResult(
        event_id=request.event_id,
        status=status,
        changes=changes_count,
        outcomes=tuple(outcomes),
    )


async def _process_entity(
    session: AsyncSession,
    request: IngestRequest,
    entity: NormalizedEntity,
) -> EntityOutcome:
    row, is_new = await ingest_repo.lock_entity(
        session=session,
        entity_type=entity.entity_type,
        entity_key=entity.entity_key,
        product_sku=entity.product_sku,
    )

    verdict = _evaluate_state_diff(
        stored_state=None if is_new else row.state,
        stored_hash=row.state_hash,
        stored_source_updated_at=row.source_updated_at,
        new_state=entity.state,
        new_hash=entity.state_hash,
        new_source_updated_at=entity.source_updated_at,
    )

    if verdict.kind == "stale":
        return EntityOutcome(
            entity_type=entity.entity_type,
            entity_key=entity.entity_key,
            outcome=verdict.kind,
            version=row.version,
        )

    if verdict.kind == "unchanged":
        await ingest_repo.touch_entity(
            session=session,
            entity_type=entity.entity_type,
            entity_key=entity.entity_key,
        )

        return EntityOutcome(
            entity_type=entity.entity_type,
            entity_key=entity.entity_key,
            outcome=verdict.kind,
            version=row.version,
        )

    next_version = row.version + 1
    await ingest_repo.update_entity(
        session=session,
        row=row,
        next_version=next_version,
        entity=entity,
    )
    await ingest_repo.append_change(
        session=session,
        entity=entity,
        version=next_version,
        diff=verdict.diff,
        source=request.source,
        source_event_id=request.event_id,
        source_updated_at=entity.source_updated_at,
    )

    return EntityOutcome(
        entity_type=entity.entity_type,
        entity_key=entity.entity_key,
        outcome=verdict.kind,
        version=next_version,
    )


def _evaluate_state_diff(
    stored_state: Mapping[str, Any] | None,
    stored_hash: str,
    stored_source_updated_at: datetime | None,
    new_state: Mapping[str, Any],
    new_hash: str,
    new_source_updated_at: datetime | None,
) -> Verdict:
    previous = stored_state or {}
    entries: list[dict[str, Any]] = []
    for name in sorted(set(previous) | set(new_state)):
        before = canonical_value(previous.get(name))
        after = canonical_value(new_state.get(name))
        if before == after:
            continue
        entries.append({"field": name, "old": before, "new": after})
    field_diff = tuple(entries)

    if stored_state is None:
        return Verdict(kind="created", diff=field_diff)

    if new_hash == stored_hash:
        return Verdict(kind="unchanged", diff=field_diff)

    if (
        stored_source_updated_at is not None
        and new_source_updated_at is not None
        and new_source_updated_at < stored_source_updated_at
    ):
        return Verdict(kind="stale", diff=field_diff)

    return Verdict(kind="changed", diff=field_diff)
