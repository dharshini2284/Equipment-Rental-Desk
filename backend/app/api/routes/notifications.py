from fastapi import APIRouter, Query

from app.api.dependencies import MAX_ID, NowDep, SessionDep
from app.api.routes import Limit, Offset, error_responses
from app.api.schemas import NotificationOut, Page, RemindersResult
from app.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationOut], responses=error_responses(400))
def list_notifications(
    session: SessionDep,
    member_id: int | None = Query(default=None, ge=1, le=MAX_ID),
    kind: str | None = Query(default=None, max_length=40),
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[NotificationOut]:
    """The SMS outbox, newest first. Delivery is a stub: nothing is actually sent."""
    rows, total = notification_service.list_notifications(
        session, member_id=member_id, kind=kind, limit=limit, offset=offset
    )
    return Page(
        items=[NotificationOut.from_model(n) for n in rows], total=total, limit=limit, offset=offset
    )


@router.post("/overdue-reminders", response_model=RemindersResult, responses=error_responses(400))
def send_overdue_reminders(session: SessionDep, now: NowDep) -> RemindersResult:
    """Queue a reminder for each overdue loan, at most one per loan per 24 hours."""
    queued, skipped = notification_service.send_overdue_reminders(session, now=now)
    return RemindersResult(queued=queued, skipped_recently_reminded=skipped)
