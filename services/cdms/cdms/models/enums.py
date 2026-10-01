import enum

from sqlalchemy.dialects.postgresql import ENUM as NativeEnum


class EntityType(str, enum.Enum):
    PRODUCT = "product"
    INVENTORY = "inventory"


class SourceChannel(str, enum.Enum):
    POLL = "poll"
    WEBHOOK = "webhook"


class ChangeStatus(str, enum.Enum):
    APPLIED = "applied"
    UNCHANGED = "unchanged"
    STALE = "stale"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


def _values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


def _native(name: str, enum_cls: type[enum.Enum]) -> NativeEnum:
    return NativeEnum(
        enum_cls,
        name=name,
        values_callable=_values,
        create_constraint=False,
    )


ENTITY_TYPE_ENUM = _native("entity_type", EntityType)
SOURCE_CHANNEL_ENUM = _native("source_channel", SourceChannel)
CHANGE_STATUS_ENUM = _native("change_status", ChangeStatus)
