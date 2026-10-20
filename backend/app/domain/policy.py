"""Numeric limits from the problem statement, in one place.

Money is always integer paise (₹1 = 100 paise) so no rupee value is ever a float.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

PAISE_PER_RUPEE = 100

# Timestamps are stored in UTC; calendar dates (e.g. a join date) are the desk's local date.
DESK_TIMEZONE = ZoneInfo("Asia/Kolkata")

RESERVATION_HOLD = timedelta(hours=48)
LOAN_PERIOD = timedelta(days=7)

LATE_FEE_PER_DAY_PAISE = 10 * PAISE_PER_RUPEE
LATE_FEE_CAP_PER_LOAN_PAISE = 200 * PAISE_PER_RUPEE

MAX_ACTIVE_LOANS = 3
# A balance strictly greater than this blocks borrowing; exactly ₹100 is still allowed.
MAX_UNPAID_BALANCE_PAISE = 100 * PAISE_PER_RUPEE
# A loan overdue by strictly more than this many days blocks borrowing.
MAX_DAYS_OVERDUE_BEFORE_BLOCK = 14
