"""Waitlist entries and the notification outbox.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.persistence.types import UTCDateTime

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WAITING_SQL = "status = 'waiting'"


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("joined_at", UTCDateTime(), nullable=False),
        sa.Column("resolved_at", UTCDateTime(), nullable=True),
        sa.Column(
            "loan_id", sa.Integer(), sa.ForeignKey("loans.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("note", sa.String(300), nullable=False),
        sa.CheckConstraint(
            "status IN ('waiting', 'fulfilled', 'skipped', 'cancelled')",
            name="ck_waitlist_entries_status",
        ),
    )
    op.create_index(
        "uq_waitlist_one_waiting_entry",
        "waitlist_entries",
        ["item_id", "member_id"],
        unique=True,
        sqlite_where=sa.text(WAITING_SQL),
        postgresql_where=sa.text(WAITING_SQL),
    )
    op.create_index(
        "ix_waitlist_item_status_joined", "waitlist_entries", ["item_id", "status", "joined_at"]
    )
    op.create_index("ix_waitlist_member_status", "waitlist_entries", ["member_id", "status"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "loan_id", sa.Integer(), sa.ForeignKey("loans.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("recipient", sa.String(20), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index(
        "ix_notifications_member_created", "notifications", ["member_id", "created_at"]
    )
    op.create_index("ix_notifications_created", "notifications", ["created_at"])
    op.create_index("ix_notifications_loan_kind", "notifications", ["loan_id", "kind"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("waitlist_entries")
