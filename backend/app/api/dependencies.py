"""Request-scoped dependencies: the database session and the clock."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Path, Request, Response
from sqlalchemy.orm import Session

from app.api.errors import BadRequestError
from app.config import Settings

TEST_CLOCK_HEADER = "X-Test-Clock"
EFFECTIVE_CLOCK_HEADER = "X-Effective-Clock"
# IDs are 32-bit in PostgreSQL; anything larger cannot exist and is rejected as invalid input.
MAX_ID = 2**31 - 1


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def resolve_now(request: Request, settings: Settings) -> tuple[datetime, bool]:
    """Return "now" for this request and whether the reviewer clock override supplied it."""
    raw = request.headers.get(TEST_CLOCK_HEADER, "").strip()
    if not raw:
        return datetime.now(UTC), False
    if not settings.allow_test_clock:
        raise BadRequestError(
            f"The {TEST_CLOCK_HEADER} header is disabled on this server.",
            code="TEST_CLOCK_DISABLED",
        )
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise BadRequestError(
            f"{TEST_CLOCK_HEADER} must be an ISO-8601 timestamp with a UTC offset, "
            "e.g. 2026-10-20T10:00:00+05:30.",
            code="INVALID_TEST_CLOCK",
            details={"value": raw[:64]},
        )
    return parsed.astimezone(UTC), True


def get_now(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> datetime:
    now, overridden = resolve_now(request, settings)
    request.state.test_clock = overridden
    response.headers[EFFECTIVE_CLOCK_HEADER] = now.isoformat()
    return now


SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(get_now)]
MemberIdPath = Annotated[int, Path(ge=1, le=MAX_ID, description="Member id")]
ItemIdPath = Annotated[int, Path(ge=1, le=MAX_ID, description="Item id")]
LoanIdPath = Annotated[int, Path(ge=1, le=MAX_ID, description="Loan id")]
