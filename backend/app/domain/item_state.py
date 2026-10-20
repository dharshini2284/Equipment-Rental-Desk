"""The item state machine.

    Available --reserve--> Reserved --check_out--> Checked Out --return--> Available
                               |                        |
                               | (48h pass)             | (due_at passes)
                               v                        v
                           Available                 Overdue --return--> Available

    Available / Reserved --send_to_maintenance--> Maintenance --return_to_service--> Available

    Members can join the waitlist of any item that is not Available. Whenever the item
    becomes Available again, the first eligible member in line is reserved it automatically.
    Checked Out / Overdue reach Maintenance through a return with send_to_maintenance=true.

Expiry and overdue are derived from the clock whenever the status is read, so no
background job is needed for them to be correct.
"""

from datetime import datetime

from app.domain.errors import InvalidTransitionError
from app.domain.statuses import ItemAction, ItemStatus, LoanStatus
from app.domain.timing import is_overdue, is_reservation_expired

ALLOWED_ACTIONS: dict[ItemStatus, tuple[ItemAction, ...]] = {
    ItemStatus.AVAILABLE: (ItemAction.RESERVE, ItemAction.SEND_TO_MAINTENANCE),
    ItemStatus.RESERVED: (
        ItemAction.CHECK_OUT,
        ItemAction.CANCEL_RESERVATION,
        ItemAction.SEND_TO_MAINTENANCE,
        ItemAction.JOIN_WAITLIST,
    ),
    ItemStatus.CHECKED_OUT: (ItemAction.RETURN, ItemAction.JOIN_WAITLIST),
    ItemStatus.OVERDUE: (ItemAction.RETURN, ItemAction.JOIN_WAITLIST),
    ItemStatus.MAINTENANCE: (ItemAction.RETURN_TO_SERVICE, ItemAction.JOIN_WAITLIST),
}

_HINTS: dict[tuple[ItemStatus, ItemAction], str] = {
    (ItemStatus.CHECKED_OUT, ItemAction.SEND_TO_MAINTENANCE): (
        "Record the return first; a return can send the item straight to maintenance."
    ),
    (ItemStatus.OVERDUE, ItemAction.SEND_TO_MAINTENANCE): (
        "Record the return first; a return can send the item straight to maintenance."
    ),
    (
        ItemStatus.AVAILABLE,
        ItemAction.CHECK_OUT,
    ): "Reserve the item for a member before checking it out.",
    (
        ItemStatus.AVAILABLE,
        ItemAction.RETURN,
    ): "The item is not checked out, so it cannot be returned.",
    (ItemStatus.RESERVED, ItemAction.RETURN): "The item is reserved, not checked out.",
    (ItemStatus.AVAILABLE, ItemAction.JOIN_WAITLIST): (
        "The item is available now, so reserve it instead of queueing."
    ),
}


def effective_item_status(
    stored_status: ItemStatus,
    open_loan_reserved_at: datetime | None,
    open_loan_due_at: datetime | None,
    now: datetime,
) -> ItemStatus:
    """Combine the stored status with the clock to get the status the desk should see."""
    if (
        stored_status == ItemStatus.RESERVED
        and open_loan_reserved_at is not None
        and is_reservation_expired(open_loan_reserved_at, now)
    ):
        return ItemStatus.AVAILABLE
    if (
        stored_status == ItemStatus.CHECKED_OUT
        and open_loan_due_at is not None
        and is_overdue(open_loan_due_at, now)
    ):
        return ItemStatus.OVERDUE
    return stored_status


def effective_loan_status(
    stored_status: LoanStatus,
    reserved_at: datetime,
    due_at: datetime | None,
    now: datetime,
) -> LoanStatus:
    if stored_status == LoanStatus.RESERVED and is_reservation_expired(reserved_at, now):
        return LoanStatus.EXPIRED
    if stored_status == LoanStatus.CHECKED_OUT and due_at is not None and is_overdue(due_at, now):
        return LoanStatus.OVERDUE
    return stored_status


LOAN_ALLOWED_ACTIONS: dict[LoanStatus, tuple[ItemAction, ...]] = {
    LoanStatus.RESERVED: (ItemAction.CHECK_OUT, ItemAction.CANCEL_RESERVATION),
    LoanStatus.CHECKED_OUT: (ItemAction.RETURN,),
    LoanStatus.OVERDUE: (ItemAction.RETURN,),
    LoanStatus.RETURNED: (),
    LoanStatus.CANCELLED: (),
    LoanStatus.EXPIRED: (),
}


def ensure_loan_action_allowed(loan_id: int, status: LoanStatus, action: ItemAction) -> None:
    """Reject check-out / return / cancel on a loan that is not in the right state.

    A lapsed reservation gets its own error code so the desk can tell the member
    why, rather than a generic "invalid transition".
    """
    if action in LOAN_ALLOWED_ACTIONS[status]:
        return
    details = {"loan_id": loan_id, "current_status": status.value, "action": action.value}
    action_text = action.value.replace("_", " ")
    if status == LoanStatus.EXPIRED:
        raise InvalidTransitionError(
            f"Cannot {action_text} loan {loan_id}: the 48-hour reservation has expired.",
            code="RESERVATION_EXPIRED",
            details=details,
        )
    raise InvalidTransitionError(
        f"Cannot {action_text} loan {loan_id}: it is {status.value.replace('_', ' ')}.",
        details=details,
    )


def allowed_actions(status: ItemStatus) -> tuple[ItemAction, ...]:
    return ALLOWED_ACTIONS[status]


def ensure_action_allowed(status: ItemStatus, action: ItemAction, *, item_id: int) -> None:
    if action in ALLOWED_ACTIONS[status]:
        return
    message = (
        f"Cannot {action.value.replace('_', ' ')} an item that is {status.value.replace('_', ' ')}."
    )
    hint = _HINTS.get((status, action))
    if hint:
        message = f"{message} {hint}"
    raise InvalidTransitionError(
        message,
        details={
            "item_id": item_id,
            "current_status": status.value,
            "action": action.value,
            "allowed_actions": [a.value for a in ALLOWED_ACTIONS[status]],
        },
    )
