from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import MemberIdPath, NowDep, SessionDep
from app.api.routes import Limit, Offset, SearchText, error_responses
from app.api.schemas import (
    MemberCreate,
    MemberDetailOut,
    MemberOut,
    MemberUpdate,
    Page,
    PaymentCreate,
    PaymentOut,
    PaymentResult,
    StatementOut,
    StatusChangeRequest,
)
from app.domain.statuses import MemberStatus
from app.reports.statement_pdf import render_statement_pdf
from app.services import members as member_service
from app.services import payments as payment_service

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=Page[MemberOut], responses=error_responses(400))
def list_members(
    session: SessionDep,
    q: SearchText = None,
    member_status: MemberStatus | None = Query(default=None, alias="status"),
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[MemberOut]:
    views, total = member_service.list_members(
        session, search=q, status=member_status, limit=limit, offset=offset
    )
    return Page(
        items=[MemberOut.from_view(v) for v in views], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 409, 422),
)
def create_member(body: MemberCreate, session: SessionDep, now: NowDep) -> MemberOut:
    view = member_service.create_member(
        session,
        new_member=member_service.NewMember(
            name=body.name, phone=body.phone, joined_on=body.joined_on
        ),
        now=now,
    )
    return MemberOut.from_view(view)


@router.get("/{member_id}", response_model=MemberDetailOut, responses=error_responses(400, 404))
def get_member(member_id: MemberIdPath, session: SessionDep, now: NowDep) -> MemberDetailOut:
    """Member with balance, active-loan count and why they cannot borrow (if blocked)."""
    return MemberDetailOut.from_detail(
        member_service.get_member_detail(session, member_id=member_id, now=now)
    )


@router.patch("/{member_id}", response_model=MemberOut, responses=error_responses(400, 404, 409))
def update_member(
    member_id: MemberIdPath, body: MemberUpdate, session: SessionDep, now: NowDep
) -> MemberOut:
    view = member_service.update_member(
        session, member_id=member_id, changes=body.changes(), now=now
    )
    return MemberOut.from_view(view)


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 404, 409),
)
def delete_member(member_id: MemberIdPath, session: SessionDep) -> Response:
    """Only members with no loans or payments can be deleted; suspend the others."""
    member_service.delete_member(session, member_id=member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{member_id}/suspend",
    response_model=MemberDetailOut,
    responses=error_responses(400, 404, 409),
)
def suspend_member(
    member_id: MemberIdPath, body: StatusChangeRequest, session: SessionDep, now: NowDep
) -> MemberDetailOut:
    return MemberDetailOut.from_detail(
        member_service.suspend_member(session, member_id=member_id, reason=body.reason, now=now)
    )


@router.post(
    "/{member_id}/reinstate",
    response_model=MemberDetailOut,
    responses=error_responses(400, 404, 409),
)
def reinstate_member(
    member_id: MemberIdPath, body: StatusChangeRequest, session: SessionDep, now: NowDep
) -> MemberDetailOut:
    return MemberDetailOut.from_detail(
        member_service.reinstate_member(session, member_id=member_id, reason=body.reason, now=now)
    )


@router.get(
    "/{member_id}/statement", response_model=StatementOut, responses=error_responses(400, 404)
)
def get_statement(member_id: MemberIdPath, session: SessionDep, now: NowDep) -> StatementOut:
    """All loans, fees and payments for one member, with the running balance."""
    return StatementOut.from_view(
        member_service.get_statement(session, member_id=member_id, now=now)
    )


@router.get(
    "/{member_id}/statement.pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Statement as a PDF"},
        **error_responses(400, 404),
    },
)
def get_statement_pdf(member_id: MemberIdPath, session: SessionDep, now: NowDep) -> Response:
    """The same statement as a printable A4 PDF."""
    statement = member_service.get_statement(session, member_id=member_id, now=now)
    pdf = render_statement_pdf(statement, generated_at=now)
    filename = f"statement-member-{member_id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{member_id}/payments",
    response_model=PaymentResult,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 404, 422),
)
def record_payment(
    member_id: MemberIdPath, body: PaymentCreate, session: SessionDep, now: NowDep
) -> PaymentResult:
    payment, balance = payment_service.record_payment(
        session, member_id=member_id, amount_paise=body.amount_paise, note=body.note, now=now
    )
    return PaymentResult(payment=PaymentOut.model_validate(payment), fee_balance_paise=balance)
