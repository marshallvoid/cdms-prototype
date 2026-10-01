"""initial CDMS schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-30

Tables:
  entity_current     one row per tracked entity; the state a new observation is diffed against
  changes            append-only log, one row per real state transition
  ingestion_events   idempotency ledger; its primary key is the exactly-once guard
  poll_runs          one row per inventory sweep
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITY_TYPE = postgresql.ENUM("product", "inventory", name="entity_type", create_type=False)
SOURCE_CHANNEL = postgresql.ENUM("poll", "webhook", name="source_channel", create_type=False)
CHANGE_STATUS = postgresql.ENUM(
    "applied",
    "unchanged",
    "stale",
    "duplicate",
    "rejected",
    name="change_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (ENTITY_TYPE, SOURCE_CHANNEL, CHANGE_STATUS):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "entity_current",
        sa.Column("entity_type", ENTITY_TYPE, nullable=False),
        sa.Column("entity_key", sa.Text(), nullable=False),
        sa.Column("product_sku", sa.Text(), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("entity_type", "entity_key", name="pk_entity_current"),
    )
    op.create_index("entity_current_sku_idx", "entity_current", ["product_sku"])

    op.create_table(
        "changes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_type", ENTITY_TYPE, nullable=False),
        sa.Column("entity_key", sa.Text(), nullable=False),
        sa.Column("product_sku", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", SOURCE_CHANNEL, nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_changes"),
        sa.UniqueConstraint("entity_type", "entity_key", "version", name="uq_changes_entity_version"),
    )
    op.create_index("changes_sku_observed_idx", "changes", ["product_sku", "observed_at"])
    op.create_index(
        "changes_source_event_idx",
        "changes",
        ["source_event_id"],
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )

    op.create_table(
        "ingestion_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("source", SOURCE_CHANNEL, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=True),
        sa.Column("entity_keys", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("status", CHANGE_STATUS, nullable=False),
        sa.Column("changes_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("event_id", name="pk_ingestion_events"),
    )
    op.create_index("ingestion_source_received_idx", "ingestion_events", ["source", "received_at"])

    op.create_table(
        "poll_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("triggered_by", sa.Text(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("entities_seen", sa.Integer(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("changed", sa.Integer(), nullable=False),
        sa.Column("unchanged", sa.Integer(), nullable=False),
        sa.Column("stale", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name="pk_poll_runs"),
    )
    op.create_index("poll_runs_started_idx", "poll_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("poll_runs")
    op.drop_table("ingestion_events")
    op.drop_table("changes")
    op.drop_table("entity_current")
    bind = op.get_bind()
    for enum in (CHANGE_STATUS, SOURCE_CHANNEL, ENTITY_TYPE):
        enum.drop(bind, checkfirst=True)
