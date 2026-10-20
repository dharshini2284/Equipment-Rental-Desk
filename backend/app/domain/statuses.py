from enum import StrEnum


class MemberStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ItemStatus(StrEnum):
    """Item states as the desk sees them.

    OVERDUE is never stored: it is derived from a CHECKED_OUT item whose loan is
    past due. Likewise a stored RESERVED item whose hold has lapsed reads as
    AVAILABLE. See ``item_state.effective_item_status``.
    """

    AVAILABLE = "available"
    RESERVED = "reserved"
    CHECKED_OUT = "checked_out"
    OVERDUE = "overdue"
    MAINTENANCE = "maintenance"


STORED_ITEM_STATUSES = (
    ItemStatus.AVAILABLE,
    ItemStatus.RESERVED,
    ItemStatus.CHECKED_OUT,
    ItemStatus.MAINTENANCE,
)


class LoanStatus(StrEnum):
    """Loan lifecycle. OVERDUE and EXPIRED can be derived from the clock.

    EXPIRED is also stored once a write touches a lapsed reservation, so that
    the "one open loan per item" index stays meaningful.
    """

    RESERVED = "reserved"
    CHECKED_OUT = "checked_out"
    OVERDUE = "overdue"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


STORED_LOAN_STATUSES = (
    LoanStatus.RESERVED,
    LoanStatus.CHECKED_OUT,
    LoanStatus.RETURNED,
    LoanStatus.CANCELLED,
    LoanStatus.EXPIRED,
)
OPEN_LOAN_STATUSES = (LoanStatus.RESERVED, LoanStatus.CHECKED_OUT)


class ItemAction(StrEnum):
    RESERVE = "reserve"
    CHECK_OUT = "check_out"
    RETURN = "return"
    CANCEL_RESERVATION = "cancel_reservation"
    SEND_TO_MAINTENANCE = "send_to_maintenance"
    RETURN_TO_SERVICE = "return_to_service"
    JOIN_WAITLIST = "join_waitlist"


class WaitlistStatus(StrEnum):
    WAITING = "waiting"
    FULFILLED = "fulfilled"  # reached the front and got a reservation
    SKIPPED = "skipped"  # reached the front but could not borrow at that moment
    CANCELLED = "cancelled"  # left the queue
