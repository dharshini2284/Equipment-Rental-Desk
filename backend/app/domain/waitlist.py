"""Who may join a waitlist. Promotion order and eligibility live in services/waitlist.py."""

from app.domain.errors import ConflictError
from app.domain.item_state import ensure_action_allowed
from app.domain.statuses import ItemAction, ItemStatus


def ensure_can_join_waitlist(
    item_status: ItemStatus,
    *,
    item_id: int,
    member_id: int,
    already_waiting: bool,
    holds_item: bool,
) -> None:
    """Queueing only makes sense for an item the member can't simply reserve now."""
    ensure_action_allowed(item_status, ItemAction.JOIN_WAITLIST, item_id=item_id)
    details = {"item_id": item_id, "member_id": member_id}
    if holds_item:
        raise ConflictError(
            "This member already has the item reserved or checked out.",
            code="ALREADY_HOLDS_ITEM",
            details=details,
        )
    if already_waiting:
        raise ConflictError(
            "This member is already on the item's waitlist.",
            code="ALREADY_ON_WAITLIST",
            details=details,
        )
