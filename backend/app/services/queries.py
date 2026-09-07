from __future__ import annotations

import uuid

from sqlmodel import Session, col, func, select

from app.models import IngestionRun, IngestionSource, MealType, Order, OrderEvent, OrderStatus


def list_orders(
    session: Session,
    *,
    source: IngestionSource | None = None,
    order_status: OrderStatus | None = None,
    restaurant: str | None = None,
    meal: MealType | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Order], int]:
    """Filtered, paginated order listing for the dashboard and `GET /orders`."""
    query = select(Order)
    count_query = select(func.count()).select_from(Order)
    if source is not None:
        query = query.where(Order.source == source)
        count_query = count_query.where(Order.source == source)
    if order_status is not None:
        query = query.where(Order.status == order_status)
        count_query = count_query.where(Order.status == order_status)
    if restaurant is not None:
        query = query.where(Order.restaurant == restaurant)
        count_query = count_query.where(Order.restaurant == restaurant)
    if meal is not None:
        query = query.where(Order.meal == meal)
        count_query = count_query.where(Order.meal == meal)

    total = session.exec(count_query).one()
    orders = session.exec(query.order_by(col(Order.created_at).desc()).offset(offset).limit(limit)).all()
    return list(orders), total


def get_order_by_id(session: Session, order_id: uuid.UUID) -> Order | None:
    return session.get(Order, order_id)


def list_order_events(session: Session, order_id: uuid.UUID) -> list[OrderEvent]:
    return list(
        session.exec(
            select(OrderEvent).where(OrderEvent.order_id == order_id).order_by(col(OrderEvent.created_at))
        ).all()
    )


def list_ingestion_runs(session: Session, *, offset: int = 0, limit: int = 50) -> tuple[list[IngestionRun], int]:
    total = session.exec(select(func.count()).select_from(IngestionRun)).one()
    runs = session.exec(
        select(IngestionRun).order_by(col(IngestionRun.started_at).desc()).offset(offset).limit(limit)
    ).all()
    return list(runs), total


def list_distinct_restaurants(session: Session) -> list[str]:
    rows = session.exec(select(Order.restaurant).where(col(Order.restaurant).is_not(None)).distinct()).all()
    return sorted({r for r in rows if r})
