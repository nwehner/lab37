from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    IngestionRunOutcome,
    IngestionSource,
    ItemStatus,
    MealType,
    OrderEventType,
    OrderStatus,
)


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_item_id: str | None
    name: str
    category: str | None
    price: float | None
    status: ItemStatus | None


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: IngestionSource
    external_id: str | None
    status: OrderStatus
    delivery_platform: str | None
    restaurant: str | None
    customer_first_name: str | None
    customer_last_name: str | None
    notes: str | None
    total: float | None
    meal: MealType | None
    for_tomorrow: bool | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead]


class OrderListResponse(BaseModel):
    items: list[OrderRead]
    total: int
    offset: int
    limit: int


class OrderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    event_type: OrderEventType
    source: IngestionSource
    detail: dict[str, Any]
    created_at: datetime


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: IngestionSource
    started_at: datetime
    finished_at: datetime | None
    outcome: IngestionRunOutcome
    records_created: int
    records_updated: int
    warnings_count: int
    message: str | None


class IngestionRunListResponse(BaseModel):
    items: list[IngestionRunRead]
    total: int
    offset: int
    limit: int


class CsvUploadSummary(BaseModel):
    filename: str
    rows_ingested: int
    rows_with_warnings: int
