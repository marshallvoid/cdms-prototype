import asyncio
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from faker import Faker

from .models import CategoryBriefItemDto

_CATEGORY_POOL = [
    ("CATEGORY001", "Electronics"),
    ("CATEGORY002", "Apparel"),
    ("CATEGORY003", "Home Goods"),
    ("CATEGORY004", "Grocery"),
    ("CATEGORY005", "Sports"),
]

_MUTABLE_PRODUCT_FIELDS = ("productName", "color", "size", "description", "isActive")

_QTY_ATTRIBUTE_BY_FIELD = {
    "physicalQty": "physical_qty",
    "availableQty": "available_qty",
    "pendingInQty": "pending_in_qty",
    "pendingOutQty": "pending_out_qty",
    "freezeQty": "freeze_qty",
    "inTransitQty": "in_transit_qty",
}

_QTY_FIELD = tuple(_QTY_ATTRIBUTE_BY_FIELD.keys())


@dataclass(slots=True)
class ProductRecord:
    product_id: int
    sku: str
    partner_sku: str
    product_name: str
    asset_type: str = "Single"
    has_serial: bool = False
    has_expiration: bool = False
    color: str | None = None
    size: str | None = None
    description: str | None = None
    is_active: bool = True
    units: list[str] = field(default_factory=list)
    categories: list[CategoryBriefItemDto] = field(default_factory=list)
    outbound_type: str = "NotDefined"
    is_physical: bool = True
    is_discreet: bool = False
    packing_note: str | None = None
    hs_code: str | None = None
    country_of_origin: str | None = None
    ref_code: str | None = None
    product_tax_code: str | None = None
    product_tax_name: str | None = None
    tax_rate: float | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class InventoryRecord:
    warehouse_code: str
    sku: str
    unit_code: str
    condition_type_code: str
    physical_qty: int = 0
    available_qty: int = 0
    pending_in_qty: int = 0
    pending_out_qty: int = 0
    freeze_qty: int = 0
    in_transit_qty: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def quantities(self) -> dict[str, int]:
        return {
            "physicalQty": self.physical_qty,
            "availableQty": self.available_qty,
            "pendingInQty": self.pending_in_qty,
            "pendingOutQty": self.pending_out_qty,
            "freezeQty": self.freeze_qty,
            "inTransitQty": self.in_transit_qty,
        }


class InventoryStore:
    def __init__(
        self,
        *,
        product_count: int = 200,
        seed: int = 42,
        warehouse_codes: tuple[str, ...] = ("KQ7", "KV3"),
        condition_codes: tuple[str, ...] = ("NEW", "DAMAGED"),
        unit_codes: tuple[str, ...] = ("CAI", "BOX"),
    ) -> None:
        self._lock = asyncio.Lock()
        self._product_count = product_count
        self._seed = seed
        self._warehouse_codes = warehouse_codes
        self._condition_codes = condition_codes
        self._unit_codes = unit_codes
        self._products: dict[int, ProductRecord] = {}
        self._inventory: dict[tuple[str, str, str, str], InventoryRecord] = {}
        self._sequence = 0
        self._seed_data()

    async def mutate(self, count: int, *, seed: int | None = None) -> dict[str, list[dict[str, object]]]:
        async with self._lock:
            rng = random.Random(seed if seed is not None else self._seed + self._sequence + 1)
            products_changed: list[dict[str, object]] = []
            inventory_changed: list[dict[str, object]] = []
            product_ids = sorted(self._products)
            inventory_keys = sorted(self._inventory)

            for _ in range(count):
                if product_ids and rng.random() < 0.5:
                    product = self._products[rng.choice(product_ids)]
                    field_name = rng.choice(_MUTABLE_PRODUCT_FIELDS)

                    if field_name == "isActive":
                        product.is_active = not product.is_active
                    elif field_name == "productName":
                        product.product_name = f"{product.product_name} *"
                    else:
                        setattr(product, field_name, f"{rng.randrange(1, 9999)}")

                    product.updated_at = datetime.now(UTC)
                    self._sequence += 1
                    products_changed.append(product_payload_of(product))

                elif inventory_keys:
                    key = rng.choice(inventory_keys)
                    record = self._inventory[key]
                    field_name = rng.choice(_QTY_FIELD)
                    delta = rng.randrange(-10, 11)
                    attribute = _QTY_ATTRIBUTE_BY_FIELD[field_name]
                    setattr(record, attribute, max(0, getattr(record, attribute) + delta))

                    if field_name == "physicalQty":
                        record.available_qty = max(0, record.physical_qty - record.pending_out_qty)

                    record.last_updated = datetime.now(UTC)
                    self._sequence += 1
                    inventory_changed.append(inventory_payload_of(record))

            return {"products": products_changed, "inventories": inventory_changed}

    async def reset(self) -> dict[str, int]:
        async with self._lock:
            self._seed_data()
            return self.stats()

    def stats(self) -> dict[str, int]:
        return {"products": len(self._products), "inventory_rows": len(self._inventory)}

    async def list_products(
        self,
        *,
        keyword: str | None,
        partner_skus: list[str] | None,
        skus: list[str] | None,
        page_index: int,
        page_size: int,
    ) -> list[ProductRecord]:
        async with self._lock:
            records = sorted(self._products.values(), key=lambda p: p.product_id)
            if keyword:
                needle = keyword.lower()
                records = [p for p in records if needle in p.sku.lower() or needle in p.product_name.lower()]

            if partner_skus:
                wanted = {s.strip().lower() for s in partner_skus}
                records = [p for p in records if p.partner_sku.lower() in wanted]

            if skus:
                wanted = {s.strip().lower() for s in skus}
                records = [p for p in records if p.sku.lower() in wanted]

            start = page_index * page_size
            return records[start : start + page_size]

    async def list_inventories(
        self,
        *,
        partner_skus: list[str] | None = None,
        skus: list[str] | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[InventoryRecord]:
        async with self._lock:
            records = sorted(
                self._inventory.values(),
                key=lambda r: (r.sku, r.warehouse_code, r.unit_code, r.condition_type_code),
            )

            if partner_skus:
                wanted = {s.strip().lower() for s in partner_skus}
                records = [r for r in records if r.sku.lower() in wanted]

            if skus:
                wanted = {s.strip().lower() for s in skus}
                records = [r for r in records if r.sku.lower() in wanted]

            if from_date is not None:
                records = [r for r in records if r.last_updated >= from_date]

            if to_date is not None:
                records = [r for r in records if r.last_updated <= to_date]

            return records

    async def all_inventory_keys(self) -> list[tuple[str, str, str, str]]:
        return sorted(self._inventory)

    async def product_payload(self, sku: str) -> dict[str, object] | None:
        async with self._lock:
            for candidate in self._products.values():
                if candidate.sku == sku or candidate.partner_sku == sku:
                    return product_payload_of(candidate)

            return None

    async def inventory_payload(self, sku: str) -> dict[str, object] | None:
        async with self._lock:
            for key in sorted(self._inventory):
                if key[0] == sku:
                    return inventory_payload_of(self._inventory[key])

            return None

    def _seed_data(self) -> None:
        self._products = {}
        self._inventory = {}
        self._sequence = 0
        rng = random.Random(self._seed)
        faker = Faker()
        faker.seed_instance(self._seed)
        now = datetime.now(UTC)

        for index in range(1, self._product_count + 1):
            sku = f"SKU-{index:06d}"
            category_code, category_name = _CATEGORY_POOL[(index - 1) % len(_CATEGORY_POOL)]
            product = ProductRecord(
                product_id=index,
                sku=sku,
                partner_sku=sku,
                product_name=f"{faker.word().capitalize()} {faker.word().capitalize()} {index}",
                color=faker.color_name() if rng.random() < 0.5 else None,
                size=faker.word().upper()[:3] if rng.random() < 0.4 else None,
                description=faker.sentence(nb_words=8),
                units=[self._unit_codes[0]],
                categories=[CategoryBriefItemDto(categoryCode=category_code, categoryName=category_name)],
                hs_code=f"{rng.randrange(1000, 9999)}",
                country_of_origin=faker.country(),
                ref_code=f"REF-{index:06d}",
                product_tax_code=f"TAX{rng.randrange(1, 20)}",
                tax_rate=float(rng.choice([0.0, 5.0, 8.0, 10.0])),
                updated_at=now,
            )
            self._products[product.product_id] = product

            combos = [(u, c) for u in self._unit_codes for c in self._condition_codes]
            for unit_code, condition_code in combos:
                if rng.random() < 0.35:
                    continue

                key = (sku, self._warehouse_codes[0], unit_code, condition_code)
                self._inventory[key] = self._new_inventory_row(key, rng=rng, offset=timedelta(minutes=index))

            if rng.random() < 0.4:
                key = (sku, self._warehouse_codes[1], self._unit_codes[0], self._condition_codes[0])
                self._inventory[key] = self._new_inventory_row(key, rng=rng, offset=timedelta(minutes=index + 5))

    def _new_inventory_row(
        self, key: tuple[str, str, str, str], *, rng: random.Random, offset: timedelta
    ) -> InventoryRecord:
        physical = rng.randrange(0, 300)
        pending_in = rng.randrange(0, 30)
        pending_out = rng.randrange(0, 20)
        freeze = rng.randrange(0, 10)

        return InventoryRecord(
            warehouse_code=key[1],
            sku=key[0],
            unit_code=key[2],
            condition_type_code=key[3],
            physical_qty=physical,
            available_qty=max(0, physical - pending_out - freeze),
            pending_in_qty=pending_in,
            pending_out_qty=pending_out,
            freeze_qty=freeze,
            in_transit_qty=rng.randrange(0, 15),
            last_updated=datetime.now(UTC) - offset,
        )


def product_payload_of(product: ProductRecord) -> dict[str, object]:
    return {
        "productId": product.product_id,
        "sku": product.sku,
        "partnerSKU": product.partner_sku,
        "productName": product.product_name,
        "assetType": product.asset_type,
        "hasSerial": product.has_serial,
        "hasExpiration": product.has_expiration,
        "color": product.color,
        "size": product.size,
        "description": product.description,
        "isActive": product.is_active,
        "units": list(product.units),
        "categories": [c.model_dump() for c in product.categories],
        "updatedAt": product.updated_at.isoformat() if product.updated_at else None,
    }


def inventory_payload_of(record: InventoryRecord) -> dict[str, object]:
    return {
        "warehouseCode": record.warehouse_code,
        "partnerSKU": record.sku,
        "sku": record.sku,
        "unitCode": record.unit_code,
        "conditionTypeCode": record.condition_type_code,
        **record.quantities(),
        "lastUpdatedDate": record.last_updated.isoformat(),
        "categoryCode": None,
        "categoryName": None,
    }
