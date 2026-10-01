from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response

from ..faults import FaultInjector
from ..models import InvProductBriefDto, PagedList, ProductDto
from ..services import get_faults, get_store, split_csv
from ..store import InventoryStore, inventory_payload_of, product_payload_of

router = APIRouter(prefix="/api/v1/Products", tags=["Products"])


@router.get("", response_model=list[ProductDto])
@router.get("/", response_model=list[ProductDto], include_in_schema=False)
async def list_products(
    keyword: str | None = Query(None, alias="Keyword"),
    partner_skus: str | None = Query(None, alias="PartnerSKUs"),
    skus: str | None = Query(None, alias="SKUs"),
    page_index: int = Query(0, alias="PageIndex", ge=0),
    page_size: int = Query(10, alias="PageSize", ge=1, le=1000),
    store: InventoryStore = Depends(get_store),
    faults: FaultInjector = Depends(get_faults),
) -> list[ProductDto] | Response:
    fault = await faults.gate("products")
    if fault is not None:
        return fault

    records = await store.list_products(
        keyword=keyword,
        partner_skus=split_csv(partner_skus),
        skus=split_csv(skus),
        page_index=page_index,
        page_size=page_size,
    )
    return [ProductDto.model_validate(product_payload_of(record)) for record in records]


@router.get("/inventories", response_model=PagedList)
async def get_inventories(
    partner_skus: str | None = Query(None, alias="PartnerSKUs"),
    skus: str | None = Query(None, alias="SKUs"),
    from_date: datetime | None = Query(None, alias="FromDate"),
    to_date: datetime | None = Query(None, alias="ToDate"),
    page_index: int = Query(0, alias="PageIndex", ge=0),
    page_size: int = Query(10, alias="PageSize", ge=1, le=1000),
    store: InventoryStore = Depends(get_store),
    faults: FaultInjector = Depends(get_faults),
) -> PagedList | Response:
    fault = await faults.gate("inventories")
    if fault is not None:
        return fault

    rows = await store.list_inventories(
        partner_skus=split_csv(partner_skus),
        skus=split_csv(skus),
        from_date=from_date,
        to_date=to_date,
    )
    total = len(rows)
    start = page_index * page_size
    window = rows[start : start + page_size]
    total_pages = (total + page_size - 1) // page_size if total else 0

    return PagedList(
        pageIndex=page_index,
        pageSize=page_size,
        totalCount=total,
        totalPages=total_pages,
        indexFrom=start,
        items=[InvProductBriefDto.model_validate(inventory_payload_of(row)) for row in window],
        hasPreviousPage=page_index > 0,
        hasNextPage=start + page_size < total,
    )
