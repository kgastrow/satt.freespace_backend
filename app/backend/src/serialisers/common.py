"""
Common serializer models shared across API modules.
"""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field


def normalize_email(value: str) -> str:
    """Normalize an email address for case-insensitive identity.

    Emails are case-insensitive in practice, but the storage column and the
    ``uq_user_org_email_active`` unique index are case-sensitive. Lowercasing
    (and stripping surrounding whitespace) at the validation boundary ensures
    that ``User@Example.com`` and ``user@example.com`` resolve to the same
    account on both writes and lookups.
    """
    return value.strip().lower()


# Reusable EmailStr that is validated, then normalized to a canonical form.
# Use for any inbound email that identifies an account (registration, login,
# password reset, email change, admin user create/update, lookups).
NormalizedEmail = Annotated[EmailStr, AfterValidator(normalize_email)]


class PaginatedResponse(BaseModel):
    """Base class for paginated responses."""

    total: int = Field(..., description="Total number of items")
    limit: int = Field(..., description="Maximum items per page")
    offset: int = Field(..., description="Number of items skipped")


class MessageResponse(BaseModel):
    """Generic success message response.

    Example:
        {
            "message": "Operation completed successfully",
            "message_code": "common.success"
        }
    """

    message: str = Field(..., description="Human-readable success message (English)")
    message_code: str = Field(..., description="Translation code for i18n")
