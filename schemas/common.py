"""Schemas and query types shared by all resources."""

from typing import Annotated, Generic, Self, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, model_validator

T = TypeVar("T")

Limit = Annotated[int, Query(ge=1, le=100, description="Maximum number of items to return")]
Offset = Annotated[int, Query(ge=0, description="Number of items to skip")]


class Page(BaseModel, Generic[T]):  # noqa: UP046
    """Offset-paginated collection. Ordering is deterministic (created_at, then id)."""

    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Documents the standard error contract in OpenAPI."""

    error: ErrorBody


class PatchModel(BaseModel):
    """Base for PATCH bodies: unknown fields are rejected, at least one field is required,
    and explicit nulls are rejected (a field is either omitted or given a real value)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self
