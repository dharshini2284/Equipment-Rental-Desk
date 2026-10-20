from datetime import datetime

from app.domain.policy import LATE_FEE_CAP_PER_LOAN_PAISE, LATE_FEE_PER_DAY_PAISE
from app.domain.timing import days_overdue


def late_fee_paise(due_at: datetime, returned_at: datetime, replacement_value_paise: int) -> int:
    """₹10 per late day, capped at ₹200 per loan and at the item's replacement value."""
    uncapped = days_overdue(due_at, returned_at) * LATE_FEE_PER_DAY_PAISE
    return min(uncapped, LATE_FEE_CAP_PER_LOAN_PAISE, replacement_value_paise)
