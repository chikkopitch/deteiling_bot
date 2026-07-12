from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class BookingDraft(BaseModel):
    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1980, le=2200)
    vehicle_class: str
    service_ids: list[UUID] = Field(min_length=1)
    slot_id: UUID
    customer_name: str = Field(min_length=2, max_length=80)
    customer_phone: str
    comment: str | None = Field(default=None, max_length=1000)
    photos: list["PhotoDraft"] = Field(default_factory=list)
    estimated_min: Decimal | None = Field(default=None, ge=0)
    estimated_max: Decimal | None = Field(default=None, ge=0)
    idempotency_key: str = Field(min_length=8, max_length=100)


class PriceEstimate(BaseModel):
    minimum: Decimal
    maximum: Decimal
    factors: list[str]
    calculated_at: datetime


class PhotoDraft(BaseModel):
    file_id: str = Field(min_length=1, max_length=255)
    unique_file_id: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=50)
    size_bytes: int = Field(ge=0)
