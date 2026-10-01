import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from ..models.enums import EntityType
from ..schemas.exception import InventoryUnavailable, PageCapExceeded

logger = logging.getLogger(__name__)

# path, expected top-level type, value to substitute on 404, and how to split
# the body into (page, has_next_page)
ENTITY_ROUTE_CONFIG: dict[
    EntityType,
    tuple[
        str,  # path
        type,  # expected type
        Any,  # default value
        Callable[[Any, int], tuple[list[Any], bool]],  # page extractor
    ],
] = {
    EntityType.PRODUCT: (
        "/api/v1/Products",
        list,
        [],
        lambda res, page_size: (list(res), len(res) >= page_size),
    ),
    EntityType.INVENTORY: (
        "/api/v1/Products/inventories",
        dict,
        {},
        lambda res, page_size: (
            list(res.get("items") or []),
            res.get("hasNextPage", False),
        ),
    ),
}


class InventoryClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        retries: int = 2,
        backoff: float = 0.25,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._retries = max(0, retries)
        self._backoff = backoff
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=timeout),
            headers={"accept": "application/json"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def iter_entities(
        self,
        entity_type: EntityType,
        page_size: int,
        max_pages: int,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        config = ENTITY_ROUTE_CONFIG.get(entity_type)
        if config is None:
            raise ValueError(f"unsupported entity type: {entity_type}")

        path, expected_type, default_val, page_extractor = config

        for page_index in range(max_pages):
            res = await self._get_json(
                path,
                expected_type=expected_type,
                default_val=default_val,
                params={"PageIndex": page_index, "PageSize": page_size},
            )

            page, has_next_page = page_extractor(res, page_size)
            yield page
            if not has_next_page:
                return

        raise PageCapExceeded(f"{entity_type.value} sweep exceeded {max_pages} pages of {page_size}")

    async def _get_json(
        self,
        path: str,
        *,
        expected_type: type,
        default_val: Any,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_error: str | None = None
        for attempt in range(self._retries + 1):
            try:
                response = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                last_error = str(exc)
            else:
                if response.status_code == 404:
                    return default_val

                if response.status_code < 400:
                    try:
                        body = response.json()
                    except ValueError as exc:
                        last_error = f"{path} returned a body that is not valid JSON"
                        logger.warning("malformed response from %s: %s", path, exc)
                        break

                    if not isinstance(body, expected_type):
                        last_error = f"{path} returned {type(body).__name__}, expected {expected_type.__name__}"
                        logger.warning(last_error)
                        break

                    return body

                elif response.status_code == 429 or response.status_code >= 500:
                    last_error = f"{path} returned HTTP {response.status_code}"
                else:
                    last_error = f"{path} returned HTTP {response.status_code}: {response.text[:200]}"

            if attempt < self._retries:
                await asyncio.sleep(self._backoff * (2**attempt))

        raise InventoryUnavailable(last_error or f"{path} is unreachable")
