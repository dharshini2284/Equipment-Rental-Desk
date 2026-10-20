from typing import Annotated, Any

from fastapi import Query

from app.api.schemas import ErrorResponse

Limit = Annotated[int, Query(ge=1, le=100, description="Page size (max 100)")]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]
SearchText = Annotated[str | None, Query(max_length=100, description="Case-insensitive search")]


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI entries so each endpoint documents the error codes it can return."""
    descriptions = {
        400: "Validation error or bad header",
        404: "Not found",
        409: "Invalid state transition or conflicting data",
        422: "Business rule violation",
    }
    return {
        code: {"model": ErrorResponse, "description": descriptions[code]} for code in status_codes
    }
