from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.params import EmptyStrToNone
from app.api.schemas import OrderEventRead, OrderListResponse, OrderRead
from app.db import get_session
from app.models import IngestionSource, MealType, OrderStatus
from app.services import queries
from app.services.dispatch import DispatchError, RobotDispatchPayload
from app.services.dispatch import dispatch_order as dispatch_order_service

router = APIRouter(tags=["orders"])


@router.get("/orders")
def list_orders(
    session: Annotated[Session, Depends(get_session)],
    source: Annotated[IngestionSource | None, EmptyStrToNone] = None,
    order_status: Annotated[OrderStatus | None, EmptyStrToNone] = None,
    restaurant: Annotated[str | None, EmptyStrToNone] = None,
    meal: Annotated[MealType | None, EmptyStrToNone] = None,
    offset: int = 0,
    limit: int = 50,
) -> OrderListResponse:
    orders, total = queries.list_orders(
        session,
        source=source,
        order_status=order_status,
        restaurant=restaurant,
        meal=meal,
        offset=offset,
        limit=limit,
    )
    return OrderListResponse(
        items=[OrderRead.model_validate(order) for order in orders],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/orders/{order_id}")
def get_order(
    order_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> OrderRead:
    order = queries.get_order_by_id(session, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    return OrderRead.model_validate(order)


@router.get("/orders/{order_id}/events")
def get_order_events(
    order_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[OrderEventRead]:
    order = queries.get_order_by_id(session, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    events = queries.list_order_events(session, order_id)
    return [OrderEventRead.model_validate(event) for event in events]


@router.post("/orders/{order_id}/dispatch")
def dispatch_order(
    order_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> RobotDispatchPayload:
    order = queries.get_order_by_id(session, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    try:
        return dispatch_order_service(session, order)
    except DispatchError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
