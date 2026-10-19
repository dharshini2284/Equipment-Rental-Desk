"""Database tables.

Statuses are stored as short strings guarded by CHECK constraints so the schema
reads the same on SQLite and PostgreSQL. Money columns are integer paise.
A member's fee balance is not stored: it is always derived from returned loans
minus payments (see ``queries.member_balance_paise``).
"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.persistence.types import UTCDateTime

OPEN_LOAN_SQL = "status IN ('reserved', 'checked_out')"
WAITING_SQL = "status = 'waiting'"


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="ck_members_status"),
        UniqueConstraint("phone", name="uq_members_phone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    joined_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())

    status_changes: Mapped[list["MemberStatusChange"]] = relationship(
        back_populates="member", order_by="MemberStatusChange.changed_at"
    )


class MemberStatusChange(Base):
    """Audit trail for suspensions and reinstatements; rows are never updated or deleted."""

    __tablename__ = "member_status_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(300))
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime())

    member: Mapped[Member] = relationship(back_populates="status_changes")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'reserved', 'checked_out', 'maintenance')",
            name="ck_items_status",
        ),
        CheckConstraint("replacement_value_paise > 0", name="ck_items_replacement_value_positive"),
        Index("ix_items_status", "status"),
        Index("ix_items_category", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    replacement_value_paise: Mapped[int] = mapped_column(Integer)
    condition_note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="available")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())


class Loan(Base):
    """One borrowing, from reservation to its end (returned, cancelled or expired)."""

    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'checked_out', 'returned', 'cancelled', 'expired')",
            name="ck_loans_status",
        ),
        CheckConstraint(
            "status NOT IN ('checked_out', 'returned') "
            "OR (checked_out_at IS NOT NULL AND due_at IS NOT NULL)",
            name="ck_loans_checkout_fields",
        ),
        CheckConstraint(
            "status <> 'returned' OR (returned_at IS NOT NULL AND fee_charged_paise IS NOT NULL)",
            name="ck_loans_return_fields",
        ),
        CheckConstraint(
            "fee_charged_paise IS NULL OR fee_charged_paise >= 0",
            name="ck_loans_fee_non_negative",
        ),
        # The database-level guarantee that an item is never reserved or lent twice at once,
        # even if two requests race past the service-layer checks.
        Index(
            "uq_loans_one_open_loan_per_item",
            "item_id",
            unique=True,
            sqlite_where=text(OPEN_LOAN_SQL),
            postgresql_where=text(OPEN_LOAN_SQL),
        ),
        Index("ix_loans_member_status", "member_id", "status"),
        Index("ix_loans_status_due_at", "status", "due_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    reserved_at: Mapped[datetime] = mapped_column(UTCDateTime())
    checked_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    fee_charged_paise: Mapped[int | None] = mapped_column(Integer)

    member: Mapped[Member] = relationship()
    item: Mapped[Item] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount_paise > 0", name="ck_payments_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="RESTRICT"), index=True
    )
    amount_paise: Mapped[int] = mapped_column(Integer)
    paid_at: Mapped[datetime] = mapped_column(UTCDateTime())
    note: Mapped[str] = mapped_column(String(200), default="")


class WaitlistEntry(Base):
    """A member queueing for an item that is not available.

    Resolved entries are kept (fulfilled, skipped or cancelled) so the queue's history is
    visible; only `waiting` entries form the live queue, in `joined_at` order.
    """

    __tablename__ = "waitlist_entries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('waiting', 'fulfilled', 'skipped', 'cancelled')",
            name="ck_waitlist_entries_status",
        ),
        # A member can be in an item's live queue only once.
        Index(
            "uq_waitlist_one_waiting_entry",
            "item_id",
            "member_id",
            unique=True,
            sqlite_where=text(WAITING_SQL),
            postgresql_where=text(WAITING_SQL),
        ),
        Index("ix_waitlist_item_status_joined", "item_id", "status", "joined_at"),
        Index("ix_waitlist_member_status", "member_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # The reservation created when this entry reached the front of the queue.
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id", ondelete="RESTRICT"))
    # Why the entry was skipped, e.g. the member's borrowing blocks at the time.
    note: Mapped[str] = mapped_column(String(300), default="")

    member: Mapped[Member] = relationship()
    item: Mapped[Item] = relationship()


class Notification(Base):
    """An SMS the desk would send. Delivery is stubbed: rows are the visible outbox.

    Written in the same transaction as the action that triggers it (a transactional
    outbox), so a message exists exactly when its action committed.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_member_created", "member_id", "created_at"),
        Index("ix_notifications_created", "created_at"),
        Index("ix_notifications_loan_kind", "loan_id", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"))
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(10), default="sms")
    recipient: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())

    member: Mapped[Member] = relationship()
