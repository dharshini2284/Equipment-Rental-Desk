"""Application entry point: `uvicorn app.main:app`."""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.dependencies import EFFECTIVE_CLOCK_HEADER, TEST_CLOCK_HEADER
from app.api.errors import internal_error_response, register_error_handlers
from app.api.routes import items, loans, members, notifications, system, waitlist
from app.config import Settings, get_settings
from app.logging_config import configure_logging, request_id_var
from app.persistence.database import create_db_engine, create_session_factory

API_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = logging.getLogger("app.request")


def _request_id_from(request: Request) -> str:
    """Reuse a caller's request id if it looks sane, otherwise mint one."""
    supplied = request.headers.get(REQUEST_ID_HEADER, "")
    return supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = _request_id_from(request)
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # Anything the specific handlers did not catch: log the trace, hide it from the client.
            logger.exception(
                "request.unhandled_exception",
                extra={"method": request.method, "path": request.url.path},
            )
            response = internal_error_response()
        response.headers[REQUEST_ID_HEADER] = request_id
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        # Health checks arrive every few seconds on hosted platforms; keep them out of INFO.
        level = logging.DEBUG if request.url.path.endswith("/health") else logging.INFO
        logger.log(
            level,
            "request.completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "test_clock": bool(request.headers.get(TEST_CLOCK_HEADER)),
            },
        )
        return response
    finally:
        request_id_var.reset(token)


def _openapi_with_400_validation(app: FastAPI) -> Callable[[], dict[str, Any]]:
    """FastAPI documents validation errors as 422; this API returns them as 400."""

    def build() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes
        )
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                responses = operation.get("responses", {})
                default_validation = responses.get("422", {})
                if "HTTPValidationError" in str(default_validation):
                    responses.pop("422")
                    responses.setdefault(
                        "400",
                        {
                            "description": "Validation error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    )
        app.openapi_schema = schema
        return schema

    return build


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Equipment Rental Desk API",
        version="1.0.0",
        description=(
            "Community tool library: members, items, reservations, loans, fees and payments. "
            f"Send an `{TEST_CLOCK_HEADER}` header (ISO-8601 with offset) to override 'now'."
        ),
    )
    engine = create_db_engine(settings.database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", TEST_CLOCK_HEADER, REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, EFFECTIVE_CLOCK_HEADER, "Content-Disposition"],
    )
    # Registered after CORS so it wraps it: even CORS preflights get a request id.
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    app.include_router(system.health_router)
    app.include_router(system.health_router, prefix=API_PREFIX)
    for module in (system, members, items, loans, waitlist, notifications):
        app.include_router(module.router, prefix=API_PREFIX)

    app.openapi = _openapi_with_400_validation(app)  # type: ignore[method-assign]
    logger.info(
        "app.started",
        extra={
            "database": engine.dialect.name,
            "test_clock_allowed": settings.allow_test_clock,
            "cors_origins": settings.cors_origin_list,
        },
    )
    return app


app = create_app()
