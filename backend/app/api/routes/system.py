import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import NowDep, SessionDep, get_settings_from_app
from app.api.routes import error_responses
from app.api.schemas import ClockOut, HealthOut
from app.config import Settings

# /health is mounted at the root (for the hosting platform) and under /api/v1.
health_router = APIRouter(tags=["system"])
router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@health_router.get("/health", response_model=HealthOut)
def health(session: SessionDep) -> HealthOut | JSONResponse:
    """Liveness plus a one-row database check. Returns 503 if the database is unreachable."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("health.database_unreachable")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "error"})
    finally:
        session.rollback()
    return HealthOut(status="ok", database="ok")


@router.get("/clock", response_model=ClockOut, responses=error_responses(400))
def clock(
    request: Request, now: NowDep, settings: Settings = Depends(get_settings_from_app)
) -> ClockOut:
    """The time the server is using for this request (honours X-Test-Clock)."""
    return ClockOut(
        now=now,
        test_clock_active=request.state.test_clock,
        test_clock_allowed=settings.allow_test_clock,
    )
