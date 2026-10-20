import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.errors import BusinessRuleViolation
from app.domain.money import format_rupees
from app.persistence import queries
from app.persistence.models import Payment
from app.services.notifications import Kind, notify

logger = logging.getLogger(__name__)


def record_payment(
    session: Session, *, member_id: int, amount_paise: int, note: str, now: datetime
) -> tuple[Payment, int]:
    """Record a fee payment and return it with the member's new balance.

    Paying more than is owed is refused rather than stored as credit: the desk
    has no process for refunds, and a negative balance would quietly pre-pay
    future late fees. Suspended members may still pay.
    """
    with session.begin():
        # Locking the member serialises concurrent payments, so two payments that each
        # fit the balance cannot together overpay it.
        member = queries.get_member(session, member_id, for_update=True)
        balance = queries.member_balance_paise(session, member.id)
        if amount_paise > balance:
            raise BusinessRuleViolation(
                f"Payment of {amount_paise} paise is more than the outstanding balance of "
                f"{balance} paise.",
                code="PAYMENT_EXCEEDS_BALANCE",
                details={
                    "member_id": member.id,
                    "amount_paise": amount_paise,
                    "balance_paise": balance,
                },
            )
        payment = Payment(member_id=member.id, amount_paise=amount_paise, paid_at=now, note=note)
        session.add(payment)
        session.flush()
        logger.info(
            "payment.recorded",
            extra={"member_id": member.id, "payment_id": payment.id, "amount_paise": amount_paise},
        )
        remaining = balance - amount_paise
        notify(
            session,
            member=member,
            kind=Kind.PAYMENT_RECEIVED,
            now=now,
            message=(
                f"We received {format_rupees(amount_paise)}. "
                + (f"You still owe {format_rupees(remaining)}." if remaining else "All fees paid.")
            ),
        )
        return payment, remaining
