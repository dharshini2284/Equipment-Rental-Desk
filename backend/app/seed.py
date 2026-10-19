"""Load realistic sample data: `python -m app.seed` (add `--reset` to wipe first).

History is created by calling the real services with the clock set in the past,
so every seeded loan, fee and payment obeys the same rules as live traffic.
All names and phone numbers are invented.

The seed is anchored to the moment it runs, so "overdue by 18 days" stays true
on the day a reviewer looks at it.
"""

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.logging_config import configure_logging
from app.persistence.database import create_db_engine, create_session_factory
from app.persistence.models import (
    Item,
    Loan,
    Member,
    MemberStatusChange,
    Notification,
    Payment,
    WaitlistEntry,
)
from app.services import items as item_service
from app.services import loans as loan_service
from app.services import members as member_service
from app.services import payments as payment_service
from app.services import waitlist as waitlist_service

logger = logging.getLogger("app.seed")

DAY = timedelta(days=1)
HOUR = timedelta(hours=1)


def rupees(amount: int) -> int:
    return amount * 100


ITEMS: list[tuple[str, str, int, str]] = [
    ("18V cordless drill", "Power tools", rupees(4_500), "Two batteries, charger in case."),
    ("Hammer drill", "Power tools", rupees(6_800), "Chuck key taped to handle."),
    ("Circular saw", "Power tools", rupees(7_200), "New blade fitted Sept 2026."),
    ("Jigsaw", "Power tools", rupees(3_900), ""),
    ("Tile cutter", "Power tools", rupees(5_500), "Water tray has a small crack."),
    ("Aluminium extension ladder 6 m", "Ladders", rupees(9_000), ""),
    ("Step ladder 2 m", "Ladders", rupees(3_200), ""),
    ("Petrol garden tiller", "Garden", rupees(28_000), "Use 2-stroke mix only."),
    ("Push lawn mower", "Garden", rupees(12_500), ""),
    ("Hedge trimmer", "Garden", rupees(4_200), ""),
    ("Wheelbarrow", "Garden", rupees(2_800), "Tyre pumped Oct 2026."),
    ("HD projector", "Events", rupees(32_000), "HDMI and VGA cables included."),
    ("Projector screen 100 in", "Events", rupees(6_000), ""),
    ("Folding tables (set of 4)", "Events", rupees(8_000), ""),
    ("Pressure washer", "Cleaning", rupees(11_000), ""),
    ("Wet/dry vacuum", "Cleaning", rupees(7_500), ""),
    ("Stud finder", "Hand tools", rupees(150), "Battery-free magnetic type."),
    ("Socket set (40 piece)", "Hand tools", rupees(2_400), "One 10 mm socket missing."),
    ("Soldering station", "Electronics", rupees(3_600), ""),
    ("Sewing machine", "Household", rupees(9_500), "Needle pack in drawer."),
]

# (name, phone, days since joining). The +91 98765 01xxx block is made up for this seed.
MEMBERS: list[tuple[str, str, int]] = [
    ("Aarav Menon", "+919876501001", 580),
    ("Diya Raghavan", "+919876501002", 500),
    ("Kabir Sethi", "+919876501003", 420),
    ("Meera Iyer", "+919876501004", 340),
    ("Rohan Kulkarni", "+919876501005", 270),
    ("Ananya Bose", "+919876501006", 250),
    ("Farhan Qureshi", "+919876501007", 200),
    ("Lakshmi Pillai", "+919876501008", 140),
    ("Vikram Joshi", "+919876501009", 100),
    ("Neha Deshpande", "+919876501010", 75),
]


@dataclass
class Seeder:
    session_factory: sessionmaker[Session]
    now: datetime

    def __post_init__(self) -> None:
        self.member_ids: dict[str, int] = {}
        self.item_ids: dict[str, int] = {}

    def _session(self) -> Session:
        return self.session_factory()

    def add_catalogue(self) -> None:
        for name, category, value, note in ITEMS:
            with self._session() as session:
                view = item_service.create_item(
                    session,
                    fields=item_service.ItemFields(name, category, value, note),
                    now=self.now - 600 * DAY,
                )
                self.item_ids[name] = view.item.id
        for name, phone, days_since_joining in MEMBERS:
            with self._session() as session:
                # Registered on the day they joined, so joined_on defaults to that date.
                view = member_service.create_member(
                    session,
                    new_member=member_service.NewMember(name, phone, joined_on=None),
                    now=self.now - days_since_joining * DAY,
                )
                self.member_ids[name] = view.member.id

    def reserve(self, member: str, item: str, at: datetime) -> int:
        with self._session() as session:
            view = loan_service.reserve_item(
                session, member_id=self.member_ids[member], item_id=self.item_ids[item], now=at
            )
            return view.loan.id

    def borrow(self, member: str, item: str, at: datetime) -> int:
        """Reserve and hand over an hour later, the usual pattern at the desk."""
        loan_id = self.reserve(member, item, at)
        with self._session() as session:
            loan_service.check_out(session, loan_id=loan_id, now=at + HOUR)
        return loan_id

    def give_back(self, loan_id: int, at: datetime, **kwargs: object) -> None:
        with self._session() as session:
            loan_service.return_item(session, loan_id=loan_id, now=at, **kwargs)  # type: ignore[arg-type]

    def queue(self, member: str, item: str, at: datetime) -> None:
        with self._session() as session:
            waitlist_service.join_waitlist(
                session, member_id=self.member_ids[member], item_id=self.item_ids[item], now=at
            )

    def pay(self, member: str, amount_paise: int, at: datetime, note: str) -> None:
        with self._session() as session:
            payment_service.record_payment(
                session,
                member_id=self.member_ids[member],
                amount_paise=amount_paise,
                note=note,
                now=at,
            )

    def build_history(self) -> None:
        now = self.now

        # Vikram: two late returns, one capped at ₹200 and one capped at the ₹150 stud
        # finder's replacement value; both paid off.
        # Calls are made in time order so each rule check sees the history as it was then.
        ladder = self.borrow("Vikram Joshi", "Aluminium extension ladder 6 m", now - 60 * DAY)
        stud_finder = self.borrow("Vikram Joshi", "Stud finder", now - 50 * DAY)
        self.give_back(ladder, now - 60 * DAY + 7 * DAY + 25 * DAY)
        self.give_back(stud_finder, now - 50 * DAY + 7 * DAY + 20 * DAY)
        self.pay("Vikram Joshi", rupees(200), now - 15 * DAY, "Cash at desk")
        self.pay("Vikram Joshi", rupees(150), now - 10 * DAY, "UPI")

        # Meera: 12 days late -> ₹120 owed, which is over the ₹100 limit, so she is blocked.
        loan = self.borrow("Meera Iyer", "Tile cutter", now - 40 * DAY)
        self.give_back(loan, now - 40 * DAY + HOUR + 7 * DAY + 12 * DAY - 2 * HOUR)

        # Farhan: exactly ₹100 owed, which is still allowed.
        loan = self.borrow("Farhan Qureshi", "Jigsaw", now - 30 * DAY)
        self.give_back(loan, now - 30 * DAY + HOUR + 7 * DAY + 10 * DAY - 2 * HOUR)

        # Ananya: on-time return, then suspended.
        loan = self.borrow("Ananya Bose", "Sewing machine", now - 20 * DAY)
        self.give_back(loan, now - 16 * DAY)
        with self._session() as session:
            member_service.suspend_member(
                session,
                member_id=self.member_ids["Ananya Bose"],
                reason="Returned sewing machine with bent needle plate; committee review pending.",
                now=now - 15 * DAY,
            )

        # Rohan: overdue by about 18 days, so he is blocked from borrowing more.
        # Vikram is waiting for the tiller.
        self.borrow("Rohan Kulkarni", "Petrol garden tiller", now - 25 * DAY)
        self.queue("Vikram Joshi", "Petrol garden tiller", now - 9 * DAY)

        # Kabir: overdue by about 3 days, fee accruing but not yet charged. Two members
        # are queued for the drill; returning it reserves it for Farhan automatically.
        self.borrow("Kabir Sethi", "Hammer drill", now - 10 * DAY)
        self.queue("Farhan Qureshi", "Hammer drill", now - 4 * DAY)
        self.queue("Neha Deshpande", "Hammer drill", now - 2 * DAY)

        # Diya: one item out and on time, one reservation waiting.
        self.borrow("Diya Raghavan", "18V cordless drill", now - 2 * DAY)
        self.reserve("Diya Raghavan", "Folding tables (set of 4)", now - 6 * HOUR)

        # Lakshmi: at the 3-active-loan limit.
        self.borrow("Lakshmi Pillai", "Wet/dry vacuum", now - DAY)
        self.borrow("Lakshmi Pillai", "Step ladder 2 m", now - DAY)
        self.reserve("Lakshmi Pillai", "Hedge trimmer", now - HOUR)

        # Aarav: a reservation that lapsed without a write touching it (reads as available),
        # and one 47 hours old, one hour from expiring.
        self.reserve("Aarav Menon", "Pressure washer", now - 72 * HOUR)
        self.reserve("Aarav Menon", "HD projector", now - 47 * HOUR)

        # Neha: a normal returned loan, nothing owed.
        loan = self.borrow("Neha Deshpande", "Projector screen 100 in", now - 12 * DAY)
        self.give_back(loan, now - 8 * DAY)

        # Lawn mower is out of service.
        with self._session() as session:
            item_service.send_to_maintenance(
                session,
                item_id=self.item_ids["Push lawn mower"],
                now=now - 3 * DAY,
                condition_note="Blade needs sharpening; volunteer booked for Saturday.",
            )


def database_has_data(session: Session) -> bool:
    return bool(session.scalar(select(func.count(Member.id))))


def clear_database(session: Session) -> None:
    """Delete all rows. Ids restart at 1 so the README's sample ids stay valid after a reset."""
    models = (Notification, WaitlistEntry, Payment, Loan, MemberStatusChange, Item, Member)
    with session.begin():
        if session.get_bind().dialect.name == "postgresql":
            tables = ", ".join(model.__table__.name for model in models)
            session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY"))
        else:
            # SQLite hands out max(id) + 1, so emptying the tables restarts ids by itself.
            for model in models:
                session.execute(delete(model))


def seed(session_factory: sessionmaker[Session], now: datetime) -> None:
    seeder = Seeder(session_factory, now)
    seeder.add_catalogue()
    seeder.build_history()
    logger.info(
        "seed.completed",
        extra={"members": len(seeder.member_ids), "items": len(seeder.item_ids)},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Load sample data into the database.")
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        if args.reset:
            clear_database(session)
            logger.info("seed.cleared")
        elif database_has_data(session):
            logger.info("seed.skipped", extra={"reason": "database already has members"})
            return
    seed(session_factory, datetime.now(UTC))
    engine.dispose()


if __name__ == "__main__":
    main()
