import pytest

from app.domain.errors import ConflictError, InvalidTransitionError
from app.domain.statuses import ItemStatus
from app.domain.waitlist import ensure_can_join_waitlist


def join(status: ItemStatus, *, already_waiting: bool = False, holds_item: bool = False) -> None:
    ensure_can_join_waitlist(
        status, item_id=1, member_id=2, already_waiting=already_waiting, holds_item=holds_item
    )


@pytest.mark.parametrize(
    "status",
    [ItemStatus.RESERVED, ItemStatus.CHECKED_OUT, ItemStatus.OVERDUE, ItemStatus.MAINTENANCE],
)
def test_can_queue_for_anything_not_available(status: ItemStatus) -> None:
    join(status)


def test_available_item_should_be_reserved_instead() -> None:
    with pytest.raises(InvalidTransitionError, match="reserve it instead"):
        join(ItemStatus.AVAILABLE)


def test_member_holding_the_item_cannot_queue_for_it() -> None:
    with pytest.raises(ConflictError) as error:
        join(ItemStatus.CHECKED_OUT, holds_item=True)
    assert error.value.code == "ALREADY_HOLDS_ITEM"


def test_member_cannot_queue_twice() -> None:
    with pytest.raises(ConflictError) as error:
        join(ItemStatus.CHECKED_OUT, already_waiting=True)
    assert error.value.code == "ALREADY_ON_WAITLIST"
