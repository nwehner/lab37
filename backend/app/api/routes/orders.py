from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import OrderEventRead, OrderListResponse, OrderRead
from app.models import IngestionSource, MealType, OrderStatus
from app.services.dispatch import RobotDispatchPayload

router = APIRouter(tags=["orders"])


@router.get("/orders")
def list_orders(
    source: IngestionSource | None = None,
    order_status: OrderStatus | None = None,
    restaurant: str | None = None,
    meal: MealType | None = None,
    offset: int = 0,
    limit: int = 50,
) -> OrderListResponse:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="not implemented yet")


@router.get("/orders/{order_id}")
def get_order(order_id: uuid.UUID) -> OrderRead:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="not implemented yet")


@router.get("/orders/{order_id}/events")
def get_order_events(order_id: uuid.UUID) -> list[OrderEventRead]:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="not implemented yet")


@router.post("/orders/{order_id}/dispatch")
def dispatch_order(order_id: uuid.UUID) -> RobotDispatchPayload:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="not implemented yet")
