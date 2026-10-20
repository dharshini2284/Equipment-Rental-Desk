"""Request and response bodies.

Requests forbid unknown fields and use strict integers, so `"100"`, `100.5` or
`true` for an amount is a validation error rather than being silently coerced.
All money is integer paise; all timestamps are UTC ISO-8601.
"""

import re
from datetime import date, datetime
from typing import Annotated, Generic, Self, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.api.dependencies import MAX_ID
from app.domain.statuses import ItemAction, ItemStatus, LoanStatus, MemberStatus, WaitlistStatus
from app.persistence.models import Notification
from app.services.views import (
    ItemView,
    LoanView,
    MemberDetailView,
    MemberView,
    StatementView,
)
from app.services.waitlist import WaitlistEntryView

# ₹1 crore. Large enough for any tool, small enough to rule out integer overflow.
MAX_MONEY_PAISE = 1_000_000_000

_PHONE_PATTERN = re.compile(r"^\+?\d{10,15}$")


def _normalise_phone(value: str) -> str:
    compact = re.sub(r"[\s-]", "", value)
    if not _PHONE_PATTERN.fullmatch(compact):
        raise ValueError("phone must be 10-15 digits, optionally starting with +")
    return compact


PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[str, StringConstraints(max_length=25), AfterValidator(_normalise_phone)]
ItemName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
ConditionNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
PaymentNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
MoneyPaise = Annotated[int, Field(strict=True, gt=0, le=MAX_MONEY_PAISE)]
EntityId = Annotated[int, Field(strict=True, ge=1, le=MAX_ID)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatchModel(RequestModel):
    """PATCH bodies: omitted fields stay as they are, explicit nulls are rejected."""

    @model_validator(mode="after")
    def reject_empty_and_null(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("provide at least one field to change")
        nulls = [name for name in self.model_fields_set if getattr(self, name) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self

    def changes(self) -> dict[str, object]:
        return self.model_dump(exclude_unset=True)


# --- Requests --------------------------------------------------------------------------


class MemberCreate(RequestModel):
    name: PersonName
    phone: Phone
    joined_on: date | None = Field(
        default=None, description="Defaults to today's date in IST when omitted."
    )


class MemberUpdate(PatchModel):
    name: PersonName | None = None
    phone: Phone | None = None
    joined_on: date | None = None


class StatusChangeRequest(RequestModel):
    reason: Reason


class ItemCreate(RequestModel):
    name: ItemName
    category: Category
    replacement_value_paise: MoneyPaise
    condition_note: ConditionNote = ""


class ItemUpdate(PatchModel):
    name: ItemName | None = None
    category: Category | None = None
    replacement_value_paise: MoneyPaise | None = None
    condition_note: ConditionNote | None = None


class MaintenanceRequest(RequestModel):
    condition_note: ConditionNote | None = None


class ReserveRequest(RequestModel):
    member_id: EntityId
    item_id: EntityId


class ReturnRequest(RequestModel):
    send_to_maintenance: bool = Field(default=False, strict=True)
    condition_note: ConditionNote | None = None


class PaymentCreate(RequestModel):
    amount_paise: MoneyPaise
    note: PaymentNote = ""


# --- Responses -------------------------------------------------------------------------

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class MemberOut(BaseModel):
    id: int
    name: str
    phone: str
    joined_on: date
    status: MemberStatus
    created_at: datetime
    fee_balance_paise: int

    @classmethod
    def from_view(cls, view: MemberView) -> "MemberOut":
        m = view.member
        return cls(
            id=m.id,
            name=m.name,
            phone=m.phone,
            joined_on=m.joined_on,
            status=MemberStatus(m.status),
            created_at=m.created_at,
            fee_balance_paise=view.balance_paise,
        )


class BorrowingBlockOut(BaseModel):
    code: str
    message: str


class EligibilityOut(BaseModel):
    can_borrow: bool
    blocks: list[BorrowingBlockOut]


class StatusChangeOut(BaseModel):
    from_status: MemberStatus
    to_status: MemberStatus
    reason: str
    changed_at: datetime


class MemberDetailOut(MemberOut):
    active_loan_count: int
    eligibility: EligibilityOut
    status_history: list[StatusChangeOut]

    @classmethod
    def from_detail(cls, view: MemberDetailView) -> "MemberDetailOut":
        base = MemberOut.from_view(MemberView(member=view.member, balance_paise=view.balance_paise))
        return cls(
            **base.model_dump(),
            active_loan_count=view.active_loan_count,
            eligibility=EligibilityOut(
                can_borrow=view.eligibility.can_borrow,
                blocks=[
                    BorrowingBlockOut(code=b.code, message=b.message)
                    for b in view.eligibility.blocks
                ],
            ),
            status_history=[
                StatusChangeOut(
                    from_status=MemberStatus(c.from_status),
                    to_status=MemberStatus(c.to_status),
                    reason=c.reason,
                    changed_at=c.changed_at,
                )
                for c in view.status_changes
            ],
        )


class LoanOut(BaseModel):
    id: int
    member_id: int
    member_name: str
    member_phone: str
    item_id: int
    item_name: str
    status: LoanStatus
    reserved_at: datetime
    reservation_expires_at: datetime
    checked_out_at: datetime | None
    due_at: datetime | None
    returned_at: datetime | None
    cancelled_at: datetime | None
    fee_charged_paise: int | None
    days_overdue: int
    accrued_fee_paise: int = Field(
        description="Late fee if the item were returned now; 0 unless the loan is overdue."
    )

    @classmethod
    def from_view(cls, view: LoanView) -> "LoanOut":
        loan = view.loan
        return cls(
            id=loan.id,
            member_id=loan.member_id,
            member_name=loan.member.name,
            member_phone=loan.member.phone,
            item_id=loan.item_id,
            item_name=loan.item.name,
            status=view.status,
            reserved_at=loan.reserved_at,
            reservation_expires_at=view.reservation_expires_at,
            checked_out_at=loan.checked_out_at,
            due_at=loan.due_at,
            returned_at=loan.returned_at,
            cancelled_at=loan.cancelled_at,
            fee_charged_paise=loan.fee_charged_paise,
            days_overdue=view.days_overdue,
            accrued_fee_paise=view.accrued_fee_paise,
        )


class ItemOut(BaseModel):
    id: int
    name: str
    category: str
    replacement_value_paise: int
    condition_note: str
    status: ItemStatus
    created_at: datetime
    updated_at: datetime
    allowed_actions: list[ItemAction]
    current_loan: LoanOut | None

    @classmethod
    def from_view(cls, view: ItemView) -> "ItemOut":
        item = view.item
        return cls(
            id=item.id,
            name=item.name,
            category=item.category,
            replacement_value_paise=item.replacement_value_paise,
            condition_note=item.condition_note,
            status=view.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
            allowed_actions=list(view.allowed_actions),
            current_loan=LoanOut.from_view(view.current_loan) if view.current_loan else None,
        )


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    amount_paise: int
    paid_at: datetime
    note: str


class PaymentResult(BaseModel):
    payment: PaymentOut
    fee_balance_paise: int


class StatementOut(BaseModel):
    member: MemberOut
    fee_balance_paise: int
    total_fees_charged_paise: int
    total_paid_paise: int
    accrued_unbilled_fees_paise: int = Field(
        description="Late fees building up on loans still out; charged only when returned."
    )
    loans: list[LoanOut]
    payments: list[PaymentOut]

    @classmethod
    def from_view(cls, view: StatementView) -> "StatementOut":
        return cls(
            member=MemberOut.from_view(
                MemberView(member=view.member, balance_paise=view.balance_paise)
            ),
            fee_balance_paise=view.balance_paise,
            total_fees_charged_paise=view.total_fees_charged_paise,
            total_paid_paise=view.total_paid_paise,
            accrued_unbilled_fees_paise=view.accrued_unbilled_fees_paise,
            loans=[LoanOut.from_view(loan) for loan in view.loans],
            payments=[PaymentOut.model_validate(p) for p in view.payments],
        )


class ClockOut(BaseModel):
    now: datetime
    test_clock_active: bool
    test_clock_allowed: bool


class HealthOut(BaseModel):
    status: str
    database: str


class ErrorBody(BaseModel):
    type: str
    code: str
    message: str
    details: dict[str, object]
    request_id: str | None


class ErrorResponse(BaseModel):
    error: ErrorBody


# --- Waitlist and notifications --------------------------------------------------------


class JoinWaitlistRequest(RequestModel):
    member_id: EntityId
    item_id: EntityId


class WaitlistEntryOut(BaseModel):
    id: int
    item_id: int
    item_name: str
    member_id: int
    member_name: str
    status: WaitlistStatus
    position: int | None = Field(description="Place in the queue; null once resolved.")
    joined_at: datetime
    resolved_at: datetime | None
    loan_id: int | None = Field(description="The reservation made when this entry's turn came.")
    note: str

    @classmethod
    def from_view(cls, view: WaitlistEntryView) -> "WaitlistEntryOut":
        entry = view.entry
        return cls(
            id=entry.id,
            item_id=entry.item_id,
            item_name=entry.item.name,
            member_id=entry.member_id,
            member_name=entry.member.name,
            status=WaitlistStatus(entry.status),
            position=view.position,
            joined_at=entry.joined_at,
            resolved_at=entry.resolved_at,
            loan_id=entry.loan_id,
            note=entry.note,
        )


class NotificationOut(BaseModel):
    id: int
    member_id: int
    member_name: str
    loan_id: int | None
    kind: str
    channel: str
    recipient: str
    message: str
    created_at: datetime
    delivery: str = Field(
        default="stub", description="Always 'stub': messages are recorded, not actually sent."
    )

    @classmethod
    def from_model(cls, notification: Notification) -> "NotificationOut":
        return cls(
            id=notification.id,
            member_id=notification.member_id,
            member_name=notification.member.name,
            loan_id=notification.loan_id,
            kind=notification.kind,
            channel=notification.channel,
            recipient=notification.recipient,
            message=notification.message,
            created_at=notification.created_at,
        )


class RemindersResult(BaseModel):
    queued: int
    skipped_recently_reminded: int
