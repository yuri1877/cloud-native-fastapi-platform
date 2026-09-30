import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import PatchModel

MAX_EMAIL_LENGTH = 320


def _normalise_email(value: str | None) -> str | None:
    """Emails are stored lower-cased so uniqueness is effectively case-insensitive."""
    if value is None:
        return None
    if len(value) > MAX_EMAIL_LENGTH:
        raise ValueError("Email is too long")
    return value.lower()


class UserCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"email": "user@example.com", "name": "Example User"}]},
    )

    email: EmailStr
    name: str = Field(min_length=1, max_length=255)

    @field_validator("email")
    @classmethod
    def _email_lower(cls, value: str) -> str:
        return _normalise_email(value) or value


class UserUpdate(PatchModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"name": "New Name"}]},
    )

    email: EmailStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("email")
    @classmethod
    def _email_lower(cls, value: str | None) -> str | None:
        return _normalise_email(value)


class UserRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "3f2b8c1e-5a4d-4c7e-9b1a-0d6e8f2a7c11",
                    "email": "user@example.com",
                    "name": "Example User",
                    "created_at": "2026-09-19T10:00:00Z",
                    "updated_at": "2026-09-19T10:00:00Z",
                }
            ]
        },
    )

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime
    updated_at: datetime
