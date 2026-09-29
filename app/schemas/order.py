import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus
from app.schemas.common import PatchModel

# Strict ints: reject floats and numeric strings for money.
Amount = Field(
    gt=0,
    le=10**12,
    strict=True,
    description="Total in minor currency units (e.g. 1999 = 19.99). Never a float.",
)
CURRENCY_PATTERN = r"^[A-Z]{3}$"


class OrderCreate(BaseModel):
    """New orders always start as PENDING."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "user_id": "3f2b8c1e-5a4d-4c7e-9b1a-0d6e8f2a7c11",
                    "total_amount": 1999,
                    "currency": "GBP",
                }
            ]
        },
    )

    user_id: uuid.UUID
    total_amount: int = Amount
    currency: str = Field(pattern=CURRENCY_PATTERN, description="ISO 4217 code, upper case")


class OrderUpdate(PatchModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "PROCESSING"}]})

    status: OrderStatus | None = None
    total_amount: int | None = Field(default=None, gt=0, le=10**12, strict=True)
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)


class OrderRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "9c1d7a52-7e0b-4f3a-8a55-2b4c6d8e0f13",
                    "user_id": "3f2b8c1e-5a4d-4c7e-9b1a-0d6e8f2a7c11",
                    "status": "PENDING",
                    "total_amount": 1999,
                    "currency": "GBP",
                    "created_at": "2026-09-19T10:00:00Z",
                    "updated_at": "2026-09-19T10:00:00Z",
                }
            ]
        },
    )

    id: uuid.UUID
    user_id: uuid.UUID
    status: OrderStatus
    total_amount: int
    currency: str
    created_at: datetime
    updated_at: datetime
