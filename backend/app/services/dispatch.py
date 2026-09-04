from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.enums import IngestionSource, MealType


class RobotDispatchItem(BaseModel):
    name: str
    category: str | None
    quantity: int = 1


class RobotDispatchPayload(BaseModel):
    order_id: uuid.UUID
    source: IngestionSource
    restaurant: str | None
    meal: MealType | None
    requested_for: Literal["today", "tomorrow"] | None
    items: list[RobotDispatchItem]
    dispatched_at: datetime
