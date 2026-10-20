from datetime import UTC, datetime, timedelta

import pytest

from app.domain.fees import late_fee_paise

DUE_AT = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)
EXPENSIVE_ITEM = 3_200_000  # ₹32,000 projector, so only the ₹200 cap applies


def fee_after(late_by: timedelta, replacement_value_paise: int = EXPENSIVE_ITEM) -> int:
    return late_fee_paise(DUE_AT, DUE_AT + late_by, replacement_value_paise)


def test_on_time_return_is_free() -> None:
    assert fee_after(timedelta(0)) == 0


def test_early_return_is_free() -> None:
    assert late_fee_paise(DUE_AT, DUE_AT - timedelta(days=2), EXPENSIVE_ITEM) == 0


def test_one_minute_late_costs_one_full_day() -> None:
    assert fee_after(timedelta(minutes=1)) == 1_000


def test_ten_rupees_per_started_day() -> None:
    assert fee_after(timedelta(days=3)) == 3_000
    assert fee_after(timedelta(days=3, hours=1)) == 4_000


@pytest.mark.parametrize(
    ("late_by", "expected_paise"),
    [
        (timedelta(days=19), 19_000),
        (timedelta(days=20), 20_000),  # exactly at the ₹200 cap
        (timedelta(days=20, seconds=1), 20_000),  # 21 days would be ₹210, capped
        (timedelta(days=90), 20_000),
    ],
)
def test_capped_at_200_rupees_per_loan(late_by: timedelta, expected_paise: int) -> None:
    assert fee_after(late_by) == expected_paise


def test_never_more_than_replacement_value() -> None:
    # ₹150 stud finder, 20 days late: ₹200 by the daily rate, but capped at ₹150.
    assert fee_after(timedelta(days=20), replacement_value_paise=15_000) == 15_000


def test_replacement_value_cap_boundary() -> None:
    # ₹150 item: 14 days (₹140) is under the cap, 15 days (₹150) meets it, 16 days is capped.
    assert fee_after(timedelta(days=14), replacement_value_paise=15_000) == 14_000
    assert fee_after(timedelta(days=15), replacement_value_paise=15_000) == 15_000
    assert fee_after(timedelta(days=16), replacement_value_paise=15_000) == 15_000


def test_cheap_item_with_odd_paise_value() -> None:
    # A ₹5.50 replacement value caps a one-day fee below the ₹10 daily rate.
    assert fee_after(timedelta(days=1), replacement_value_paise=550) == 550


def test_fee_is_an_int() -> None:
    assert isinstance(fee_after(timedelta(days=4)), int)
