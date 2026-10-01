import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SourceChannel
from ..repositories.ingest import record_rejection
from ..schemas.exception import NormalizationError
from ..schemas.ingest import IngestRequest
from ..schemas.webhook import WebhookEvent, WebhookResponse
from ..services.ingest import ingest
from ..services.normalization import (
    normalize_inventory,
    normalize_product,
)
from .deps import Settings, get_app_settings, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["ingestion"])


@router.post("/inventory", response_model=WebhookResponse)
async def receive_inventory_event(
    request: Request,
    payload: WebhookEvent,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> Response:
    if settings.webhook_shared_secret and x_webhook_secret != settings.webhook_shared_secret:
        return JSONResponse(
            status_code=401,
            content={
                "code": "UNAUTHORIZED",
                "errorMessage": "Invalid or missing X-Webhook-Secret",
            },
        )

    try:
        ignored = settings.ignored_for(entity_type=payload.entity_type.value)
        if payload.entity_type.value == "inventory":
            entity = normalize_inventory(raw=payload.data, ignored=ignored)
        else:
            entity = normalize_product(raw=payload.data, ignored=ignored)

    except NormalizationError as exc:
        await record_rejection(
            session,
            event_id=payload.eventId,
            source=SourceChannel.WEBHOOK,
            event_type=payload.eventType,
            reason=str(exc),
        )

        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_PAYLOAD",
                "errorMessage": str(exc),
            },
        )

    request_model = IngestRequest(
        source=SourceChannel.WEBHOOK,
        event_id=payload.eventId,
        event_type=payload.eventType,
        entities=(entity,),
    )

    try:
        result = await ingest(session=session, request=request_model)
    except (DBAPIError, SQLAlchemyError) as exc:
        logger.warning("webhook %s could not be stored: %s", payload.eventId, exc)
        return JSONResponse(
            status_code=503,
            content={
                "code": "DATABASE_UNAVAILABLE",
                "errorMessage": "The change could not be stored; retry",
            },
        )

    outcome = result.outcomes[0] if result.outcomes else None
    body = WebhookResponse(
        eventId=result.event_id,
        status=result.status.value,
        changes=result.changes,
        entityKey=outcome.entity_key if outcome else None,
        entityType=outcome.entity_type.value if outcome else None,
        version=outcome.version if outcome else None,
        detail=("This event was already applied; no additional change was recorded" if result.is_duplicate else None),
    )

    return JSONResponse(status_code=200, content=body.model_dump(mode="json"))
