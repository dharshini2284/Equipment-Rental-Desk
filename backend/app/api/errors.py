"""Turns every failure into one JSON shape and one log line.

    {"error": {"type": ..., "code": ..., "message": ..., "details": {...}, "request_id": ...}}

| Source                         | type               | HTTP | Log level |
|--------------------------------|--------------------|------|-----------|
| Malformed body / params        | validation         | 400  | INFO      |
| Bad X-Test-Clock header        | bad_request        | 400  | INFO      |
| Unknown id                     | not_found          | 404  | INFO      |
| Action not valid in this state | invalid_transition | 409  | WARNING   |
| Clash with existing data       | conflict           | 409  | WARNING   |
| Policy rule forbids it         | rule_violation     | 422  | WARNING   |
| Database unreachable / locked  | unavailable        | 503  | ERROR     |
| Anything else                  | internal           | 500  | ERROR     |

Stack traces are logged, never returned.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import (
    BusinessRuleViolation,
    ConflictError,
    DomainError,
    InvalidTransitionError,
    NotFoundError,
)
from app.logging_config import request_id_var

logger = logging.getLogger("app.errors")


class BadRequestError(DomainError):
    """A request problem that pydantic cannot see, such as a malformed header."""

    default_code = "BAD_REQUEST"


# Order matters only for subclasses; these are all siblings.
_DOMAIN_ERROR_MAPPING: list[tuple[type[DomainError], str, int, int]] = [
    (BadRequestError, "bad_request", 400, logging.INFO),
    (NotFoundError, "not_found", 404, logging.INFO),
    (InvalidTransitionError, "invalid_transition", 409, logging.WARNING),
    (ConflictError, "conflict", 409, logging.WARNING),
    (BusinessRuleViolation, "rule_violation", 422, logging.WARNING),
]


def _classify(exc: DomainError) -> tuple[str, int, int]:
    """(error type, HTTP status, log level) for a domain error."""
    for error_class, error_type, status_code, level in _DOMAIN_ERROR_MAPPING:
        if isinstance(exc, error_class):
            return error_type, status_code, level
    return "domain", 400, logging.WARNING


def error_response(
    status_code: int,
    error_type: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "type": error_type,
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id_var.get(),
        }
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


def _request_context(request: Request) -> dict[str, Any]:
    return {"method": request.method, "path": request.url.path}


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    error_type, status_code, level = _classify(exc)
    logger.log(
        level,
        "request.rejected",
        extra={
            **_request_context(request),
            "error_type": error_type,
            "code": exc.code,
            "reason": exc.message,
            **{k: v for k, v in exc.details.items() if k.endswith("_id")},
        },
    )
    return error_response(status_code, error_type, exc.code, exc.message, exc.details)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    logger.info(
        "request.invalid",
        extra={**_request_context(request), "fields": [f["field"] for f in fields]},
    )
    return error_response(
        400, "validation", "VALIDATION_ERROR", "The request is not valid.", {"fields": fields}
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    """Framework-raised errors such as unknown routes (404) or wrong methods (405)."""
    assert isinstance(exc, StarletteHTTPException)
    code = {404: "ROUTE_NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, "http", code, str(exc.detail))


async def handle_integrity_error(request: Request, exc: Exception) -> JSONResponse:
    # Reached only when two requests race past the service checks and the database
    # constraint catches the second one (e.g. the one-open-loan-per-item index).
    logger.warning(
        "request.integrity_conflict",
        extra={**_request_context(request), "db_error": type(getattr(exc, "orig", exc)).__name__},
    )
    return error_response(
        409,
        "conflict",
        "CONCURRENT_UPDATE",
        "The change conflicts with another change made at the same time. Reload and try again.",
    )


async def handle_operational_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("database.unavailable", extra=_request_context(request), exc_info=exc)
    return error_response(
        503, "unavailable", "DATABASE_UNAVAILABLE", "The database is temporarily unavailable."
    )


def internal_error_response() -> JSONResponse:
    return error_response(
        500,
        "internal",
        "INTERNAL_ERROR",
        "Something went wrong on our side. Quote the request id if you report it.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(IntegrityError, handle_integrity_error)
    app.add_exception_handler(OperationalError, handle_operational_error)
