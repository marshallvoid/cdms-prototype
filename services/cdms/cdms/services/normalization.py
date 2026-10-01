import hashlib
import json
import logging
import math
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from ..models import EntityType
from ..schemas.exception import NormalizationError
from ..schemas.ingest import NormalizedEntity
from ..schemas.job import SweepCounters

logger = logging.getLogger(__name__)

FLOAT_PRECISION: Final = 6

# Fields whose element order carries no meaning. Without sorting, `["A","B"]`
# and `["B","A"]` would hash differently and register as a change every poll.
ORDER_INSENSITIVE_FIELDS = {"units", "categories"}

# Whitelist of the fields that define an entity, per entity type. Anything not
# listed here is dropped: upstream-only bookkeeping and metadata must never
# produce a change record, and keeping the list fixed bounds the size of the
# JSONB state column.
#
# Known gap: the bundled mock's `product_payload_of` emits only 13 of the 21
# product fields below, and never emits `updatedAt`. Ten of these fields are
# therefore never populated from a poll, and `source_timestamp` returns None for
# every polled product (see SOURCE_TIMESTAMP_FIELD). This is a mock-side gap,
# not a poller bug, and it makes the `stale` outcome reachable only for
# INVENTORY.
TRACKED_FIELDS: Final[dict[EntityType, tuple[str, ...]]] = {
    EntityType.PRODUCT: (
        "sku",
        "productName",
        "assetType",
        "hasSerial",
        "hasExpiration",
        "color",
        "size",
        "description",
        "isActive",
        "units",
        "categories",
        "outboundType",
        "isPhysical",
        "isDiscreet",
        "packingNote",
        "hsCode",
        "countryOfOrigin",
        "refCode",
        "productTaxCode",
        "productTaxName",
        "taxRate",
    ),
    EntityType.INVENTORY: (
        "physicalQty",
        "availableQty",
        "pendingInQty",
        "pendingOutQty",
        "freezeQty",
        "inTransitQty",
    ),
}

# The upstream's own clock, per entity type. Read to detect out-of-order
# arrivals, so a field the source does not send means staleness is not checkable
# for that entity rather than that it changed.
SOURCE_TIMESTAMP_FIELD: Final[dict[EntityType, str]] = {
    EntityType.PRODUCT: "updatedAt",
    EntityType.INVENTORY: "lastUpdatedDate",
}

KEY_SEPARATOR: Final = "|"


def canonical_value(value: Any, sort_items: bool = False) -> Any:
    """Reduce a value to a form that is equal-if-and-only-if semantically equal

    This is what makes hashing meaningful: `10` and `10.0` collapse to the same
    int, a naive and aware datetime describing the same instant collapse to the
    same UTC string, and dict key order stops mattering

    Pass `sort_items=True` for collections whose order is not meaningful (for "units" and "categories")
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return repr(value)  # repr() because these are not JSON-representable literals

        rounded = round(value, FLOAT_PRECISION)
        return int(rounded) if rounded.is_integer() else rounded

    if isinstance(value, datetime):
        # Naive timestamps are assumed UTC so aware and naive forms of the same instant compare equal
        value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value.astimezone(UTC).isoformat()

    if isinstance(value, Mapping):
        return {
            str(key): canonical_value(value=item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        items = [canonical_value(value=item) for item in value]
        # Sets have no inherent order; sorting by the serialized form also
        # handles nested dicts inside the collection.
        return sorted(items, key=_canonical_json) if sort_items else items

    return str(value)


def normalize_product(
    raw: Mapping[str, Any],
    ignored: frozenset[str] = frozenset(),
) -> NormalizedEntity:
    sku = _validate(value=raw.get("sku"), field="sku")
    return _build(
        entity_type=EntityType.PRODUCT,
        raw=raw,
        ignored=ignored,
        key=sku,
        product_sku=sku,
    )


def normalize_inventory(
    raw: Mapping[str, Any],
    ignored: frozenset[str] = frozenset(),
) -> NormalizedEntity:
    key = KEY_SEPARATOR.join(
        (
            _validate(value=raw.get("sku"), field="sku"),
            _validate(value=raw.get("warehouseCode"), field="warehouseCode").upper(),
            _validate(value=raw.get("unitCode"), field="unitCode").upper(),
            _validate(value=raw.get("conditionTypeCode"), field="conditionTypeCode").upper(),
        )
    )
    return _build(
        entity_type=EntityType.INVENTORY,
        raw=raw,
        ignored=ignored,
        key=key,
        product_sku=key.split(KEY_SEPARATOR, 1)[0],
    )


def normalise_many(
    page: list[dict[str, Any]],
    normalise: Callable[..., NormalizedEntity],
    ignored: frozenset[str],
    counters: SweepCounters,
) -> list[NormalizedEntity]:
    entities: list[NormalizedEntity] = []
    for row in page:
        try:
            entities.append(normalise(row, ignored))
        except NormalizationError as exc:
            counters.invalid += 1
            logger.debug("Skipping unusable row from the source: %s", exc)

    return entities


def _validate(value: object, *, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise NormalizationError(f"'{field}' is required to identify an entity")
    return text


def _build(
    entity_type: EntityType,
    raw: Mapping[str, Any],
    ignored: frozenset[str],
    key: str,
    product_sku: str,
) -> NormalizedEntity:
    state = _project_state(entity_type=entity_type, raw=raw, ignored=ignored)
    if entity_type is EntityType.PRODUCT:
        # Guarantee the identity is part of the stored state even if an operator
        # ignored the field, so a diff can always name what changed.
        state.setdefault("sku", product_sku)

    return NormalizedEntity(
        entity_type=entity_type,
        entity_key=key,
        product_sku=product_sku,
        state=state,
        state_hash=hashlib.sha256(_canonical_json(value=state).encode("utf-8")).hexdigest(),
        source_updated_at=_source_timestamp(entity_type=entity_type, raw=raw),
    )


def _project_state(
    entity_type: EntityType,
    raw: Mapping[str, Any],
    ignored: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    tracked_fields = tuple(name for name in TRACKED_FIELDS[entity_type] if name not in ignored)
    state: dict[str, Any] = {}

    for name in tracked_fields:
        if name not in raw:
            continue

        state[name] = canonical_value(
            value=raw[name],
            sort_items=name in ORDER_INSENSITIVE_FIELDS,
        )

    return state


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _source_timestamp(
    entity_type: EntityType,
    raw: Mapping[str, Any],
) -> datetime | None:
    field = SOURCE_TIMESTAMP_FIELD[entity_type]
    value = raw.get(field)
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError(f"'{field}' is not a valid timestamp: {value!r}") from exc

    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
