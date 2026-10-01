from datetime import datetime

from pydantic import BaseModel


class CategoryBriefItemDto(BaseModel):
    categoryCode: str
    categoryName: str


class ProductDto(BaseModel):
    productId: int
    sku: str
    partnerSKU: str | None = None
    productName: str
    assetType: str
    hasSerial: bool
    hasExpiration: bool
    color: str | None = None
    size: str | None = None
    description: str | None = None
    isActive: bool
    units: list[str]
    categories: list[CategoryBriefItemDto]
    updatedAt: datetime | None = None


class InvProductBriefDto(BaseModel):
    warehouseCode: str
    partnerSKU: str
    sku: str
    unitCode: str
    conditionTypeCode: str
    physicalQty: int
    availableQty: int
    pendingInQty: int
    pendingOutQty: int
    freezeQty: int
    inTransitQty: int
    lastUpdatedDate: datetime
    categoryCode: str | None = None
    categoryName: str | None = None


class PagedList(BaseModel):
    pageIndex: int
    pageSize: int
    totalCount: int
    totalPages: int
    indexFrom: int
    items: list[InvProductBriefDto]
    hasPreviousPage: bool
    hasNextPage: bool
