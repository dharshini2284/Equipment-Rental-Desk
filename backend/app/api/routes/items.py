from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import ItemIdPath, NowDep, SessionDep
from app.api.routes import Limit, Offset, SearchText, error_responses
from app.api.schemas import ItemCreate, ItemOut, ItemUpdate, MaintenanceRequest, Page
from app.domain.statuses import ItemStatus
from app.services import items as item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=Page[ItemOut], responses=error_responses(400))
def list_items(
    session: SessionDep,
    now: NowDep,
    q: SearchText = None,
    item_status: ItemStatus | None = Query(
        default=None,
        alias="status",
        description="Filters on the live status, so 'overdue' and lapsed reservations work.",
    ),
    category: str | None = Query(default=None, max_length=60),
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[ItemOut]:
    views, total = item_service.list_items(
        session,
        now=now,
        status=item_status,
        search=q,
        category=category,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[ItemOut.from_view(v) for v in views], total=total, limit=limit, offset=offset
    )


@router.get("/categories", response_model=list[str])
def list_categories(session: SessionDep) -> list[str]:
    return item_service.list_categories(session)


@router.post(
    "", response_model=ItemOut, status_code=status.HTTP_201_CREATED, responses=error_responses(400)
)
def create_item(body: ItemCreate, session: SessionDep, now: NowDep) -> ItemOut:
    fields = item_service.ItemFields(
        name=body.name,
        category=body.category,
        replacement_value_paise=body.replacement_value_paise,
        condition_note=body.condition_note,
    )
    return ItemOut.from_view(item_service.create_item(session, fields=fields, now=now))


@router.get("/{item_id}", response_model=ItemOut, responses=error_responses(400, 404))
def get_item(item_id: ItemIdPath, session: SessionDep, now: NowDep) -> ItemOut:
    """Item with its live status, current loan and the actions valid right now."""
    return ItemOut.from_view(item_service.get_item(session, item_id=item_id, now=now))


@router.patch("/{item_id}", response_model=ItemOut, responses=error_responses(400, 404))
def update_item(item_id: ItemIdPath, body: ItemUpdate, session: SessionDep, now: NowDep) -> ItemOut:
    """Edit descriptive fields. Status changes only through the action endpoints."""
    view = item_service.update_item(session, item_id=item_id, changes=body.changes(), now=now)
    return ItemOut.from_view(view)


@router.delete(
    "/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(400, 404, 409)
)
def delete_item(item_id: ItemIdPath, session: SessionDep) -> Response:
    """Only items that were never loaned can be deleted."""
    item_service.delete_item(session, item_id=item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{item_id}/send-to-maintenance",
    response_model=ItemOut,
    responses=error_responses(400, 404, 409),
)
def send_to_maintenance(
    item_id: ItemIdPath,
    session: SessionDep,
    now: NowDep,
    body: MaintenanceRequest | None = None,
) -> ItemOut:
    """Available or reserved items only; an active reservation is cancelled."""
    note = body.condition_note if body else None
    return ItemOut.from_view(
        item_service.send_to_maintenance(session, item_id=item_id, now=now, condition_note=note)
    )


@router.post(
    "/{item_id}/return-to-service",
    response_model=ItemOut,
    responses=error_responses(400, 404, 409),
)
def return_to_service(
    item_id: ItemIdPath,
    session: SessionDep,
    now: NowDep,
    body: MaintenanceRequest | None = None,
) -> ItemOut:
    note = body.condition_note if body else None
    return ItemOut.from_view(
        item_service.return_to_service(session, item_id=item_id, now=now, condition_note=note)
    )
