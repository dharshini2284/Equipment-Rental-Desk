from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import MAX_ID, NowDep, SessionDep
from app.api.routes import Limit, Offset, error_responses
from app.api.schemas import JoinWaitlistRequest, Page, WaitlistEntryOut
from app.domain.statuses import WaitlistStatus
from app.services import waitlist as waitlist_service

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

EntryIdPath = Annotated[int, Path(ge=1, le=MAX_ID, description="Waitlist entry id")]


@router.get("", response_model=Page[WaitlistEntryOut], responses=error_responses(400))
def list_waitlist(
    session: SessionDep,
    item_id: int | None = Query(default=None, ge=1, le=MAX_ID),
    member_id: int | None = Query(default=None, ge=1, le=MAX_ID),
    entry_status: WaitlistStatus | None = Query(default=None, alias="status"),
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[WaitlistEntryOut]:
    """Queue entries in the order members joined. Use status=waiting for the live queue."""
    views, total = waitlist_service.list_waitlist(
        session,
        item_id=item_id,
        member_id=member_id,
        status=entry_status,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[WaitlistEntryOut.from_view(v) for v in views],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=WaitlistEntryOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 404, 409, 422),
)
def join_waitlist(body: JoinWaitlistRequest, session: SessionDep, now: NowDep) -> WaitlistEntryOut:
    """Queue a member for an item that is not available. They are reserved it automatically
    when it frees up and it is their turn."""
    view = waitlist_service.join_waitlist(
        session, member_id=body.member_id, item_id=body.item_id, now=now
    )
    return WaitlistEntryOut.from_view(view)


@router.post(
    "/{entry_id}/cancel", response_model=WaitlistEntryOut, responses=error_responses(400, 404, 409)
)
def leave_waitlist(entry_id: EntryIdPath, session: SessionDep, now: NowDep) -> WaitlistEntryOut:
    return WaitlistEntryOut.from_view(
        waitlist_service.leave_waitlist(session, entry_id=entry_id, now=now)
    )
