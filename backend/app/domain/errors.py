"""Error types raised by the domain and service layers.

The API layer maps each class to one HTTP status; nothing here knows about HTTP.
"""

from typing import Any


class DomainError(Exception):
    default_code = "DOMAIN_ERROR"

    def __init__(
        self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details = details or {}


class NotFoundError(DomainError):
    default_code = "NOT_FOUND"


class InvalidTransitionError(DomainError):
    """The requested action is not valid for the current state of an item or loan."""

    default_code = "INVALID_TRANSITION"


class ConflictError(DomainError):
    """The request clashes with existing data (duplicate phone, delete with history, ...)."""

    default_code = "CONFLICT"


class BusinessRuleViolation(DomainError):
    """The request is well-formed and the state allows it, but a policy rule forbids it."""

    default_code = "BUSINESS_RULE_VIOLATION"
