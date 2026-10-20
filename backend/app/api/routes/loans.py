from fastapi import APIRouter, Query, status

from app.api.dependencies import MAX_ID, LoanIdPath, NowDep, SessionDep
from app.api.routes import Limit, Offset, error_responses
from app.api.schemas import LoanOut, Page, ReserveRequest, ReturnRequest
from app.services import loans as loan_service

router = APIRouter(prefix="/loans", tags=["loans"])


@router.get("", response_model=Page[LoanOut], responses=error_responses(400))
def list_loans(
    session: SessionDep,
    now: NowDep,
    member_id: int | None = Query(default=None, ge=1, le=MAX_ID),
    item_id: int | None = Query(default=None, ge=1, le=MAX_ID),
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[LoanOut]:
    """Loan history, newest first, optionally for one member or one item."""
    views, total = loan_service.list_loans(
        session, now=now, member_id=member_id, item_id=item_id, limit=limit, offset=offset
    )
    return Page(
        items=[LoanOut.from_view(v) for v in views], total=total, limit=limit, offset=offset
    )


@router.get("/overdue", response_model=Page[LoanOut], responses=error_responses(400))
def list_overdue_loans(
    session: SessionDep, now: NowDep, limit: Limit = 50, offset: Offset = 0
) -> Page[LoanOut]:
    """Checked-out loans past their due time, most overdue first."""
    views, total = loan_service.list_overdue_loans(session, now=now, limit=limit, offset=offset)
    return Page(
        items=[LoanOut.from_view(v) for v in views], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    response_model=LoanOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 404, 409, 422),
)
def reserve_item(body: ReserveRequest, session: SessionDep, now: NowDep) -> LoanOut:
    """Reserve an available item for a member. The hold lasts 48 hours."""
    view = loan_service.reserve_item(
        session, member_id=body.member_id, item_id=body.item_id, now=now
    )
    return LoanOut.from_view(view)


@router.get("/{loan_id}", response_model=LoanOut, responses=error_responses(400, 404))
def get_loan(loan_id: LoanIdPath, session: SessionDep, now: NowDep) -> LoanOut:
    return LoanOut.from_view(loan_service.get_loan(session, loan_id=loan_id, now=now))


@router.post(
    "/{loan_id}/checkout",
    response_model=LoanOut,
    responses=error_responses(400, 404, 409, 422),
)
def check_out(loan_id: LoanIdPath, session: SessionDep, now: NowDep) -> LoanOut:
    """Hand over a reserved item. Due 7 days from now."""
    return LoanOut.from_view(loan_service.check_out(session, loan_id=loan_id, now=now))


@router.post(
    "/{loan_id}/return",
    response_model=LoanOut,
    responses=error_responses(400, 404, 409),
)
def return_item(
    loan_id: LoanIdPath,
    session: SessionDep,
    now: NowDep,
    body: ReturnRequest | None = None,
) -> LoanOut:
    """Record a return, charge any late fee to the member, and free the item."""
    body = body or ReturnRequest()
    view = loan_service.return_item(
        session,
        loan_id=loan_id,
        now=now,
        send_to_maintenance=body.send_to_maintenance,
        condition_note=body.condition_note,
    )
    return LoanOut.from_view(view)


@router.post(
    "/{loan_id}/cancel",
    response_model=LoanOut,
    responses=error_responses(400, 404, 409),
)
def cancel_reservation(loan_id: LoanIdPath, session: SessionDep, now: NowDep) -> LoanOut:
    return LoanOut.from_view(loan_service.cancel_reservation(session, loan_id=loan_id, now=now))
