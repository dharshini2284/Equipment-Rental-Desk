"""Initial schema: members, status history, items, loans, payments.

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.persistence.types import UTCDateTime

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPEN_LOAN_SQL = "status IN ('reserved', 'checked_out')"


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_members_status"),
        sa.UniqueConstraint("phone", name="uq_members_phone"),
    )

    op.create_table(
        "member_status_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(16), nullable=False),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("changed_at", UTCDateTime(), nullable=False),
    )
    op.create_index(
        "ix_member_status_changes_member_id", "member_status_changes", ["member_id"]
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("replacement_value_paise", sa.Integer(), nullable=False),
        sa.Column("condition_note", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('available', 'reserved', 'checked_out', 'maintenance')",
            name="ck_items_status",
        ),
        sa.CheckConstraint(
            "replacement_value_paise > 0", name="ck_items_replacement_value_positive"
        ),
    )
    op.create_index("ix_items_status", "items", ["status"])
    op.create_index("ix_items_category", "items", ["category"])

    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reserved_at", UTCDateTime(), nullable=False),
        sa.Column("checked_out_at", UTCDateTime(), nullable=True),
        sa.Column("due_at", UTCDateTime(), nullable=True),
        sa.Column("returned_at", UTCDateTime(), nullable=True),
        sa.Column("cancelled_at", UTCDateTime(), nullable=True),
        sa.Column("fee_charged_paise", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('reserved', 'checked_out', 'returned', 'cancelled', 'expired')",
            name="ck_loans_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('checked_out', 'returned') "
            "OR (checked_out_at IS NOT NULL AND due_at IS NOT NULL)",
            name="ck_loans_checkout_fields",
        ),
        sa.CheckConstraint(
            "status <> 'returned' OR (returned_at IS NOT NULL AND fee_charged_paise IS NOT NULL)",
            name="ck_loans_return_fields",
        ),
        sa.CheckConstraint(
            "fee_charged_paise IS NULL OR fee_charged_paise >= 0",
            name="ck_loans_fee_non_negative",
        ),
    )
    op.create_index("ix_loans_item_id", "loans", ["item_id"])
    op.create_index("ix_loans_member_status", "loans", ["member_id", "status"])
    op.create_index("ix_loans_status_due_at", "loans", ["status", "due_at"])
    op.create_index(
        "uq_loans_one_open_loan_per_item",
        "loans",
        ["item_id"],
        unique=True,
        sqlite_where=sa.text(OPEN_LOAN_SQL),
        postgresql_where=sa.text(OPEN_LOAN_SQL),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("paid_at", UTCDateTime(), nullable=False),
        sa.Column("note", sa.String(200), nullable=False),
        sa.CheckConstraint("amount_paise > 0", name="ck_payments_amount_positive"),
    )
    op.create_index("ix_payments_member_id", "payments", ["member_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("loans")
    op.drop_table("items")
    op.drop_table("member_status_changes")
    op.drop_table("members")
