from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlmodel import Session

from app.models import Order, OrderEvent, OrderEventType, OrderStatus
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


class DispatchError(Exception):
    """`order` isn't in a dispatchable state."""


def dispatch_order(session: Session, order: Order) -> RobotDispatchPayload:
    """Transition `order` to `DISPATCHED` and build its robot payload.

    Rejects (`DispatchError`) an order that's already dispatched, cancelled, or
    has no items — otherwise builds the skeleton payload, appends an
    `ORDER_DISPATCHED` event carrying that payload as `detail`, and commits.
    """
    if order.status == OrderStatus.DISPATCHED:
        raise DispatchError("order is already dispatched")
    if order.status == OrderStatus.CANCELLED:
        raise DispatchError("cancelled orders cannot be dispatched")
    if not order.items:
        raise DispatchError("order has no items to dispatch")

    payload = _build_payload(order)

    order.status = OrderStatus.DISPATCHED
    order.updated_at = datetime.now(UTC)
    session.add(order)
    session.add(
        OrderEvent(
            order_id=order.id,
            event_type=OrderEventType.ORDER_DISPATCHED,
            source=order.source,
            detail=payload.model_dump(mode="json"),
        )
    )
    session.commit()
    session.refresh(order)
    return payload


def _build_payload(order: Order) -> RobotDispatchPayload:
    requested_for: Literal["today", "tomorrow"] | None = None
    if order.for_tomorrow is not None:
        requested_for = "tomorrow" if order.for_tomorrow else "today"

    return RobotDispatchPayload(
        order_id=order.id,
        source=order.source,
        restaurant=order.restaurant,
        meal=order.meal,
        requested_for=requested_for,
        items=[RobotDispatchItem(name=item.name, category=item.category) for item in order.items],
        dispatched_at=datetime.now(UTC),
    )
