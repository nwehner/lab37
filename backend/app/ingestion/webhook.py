from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from app.models import (
    IngestionRun,
    IngestionRunOutcome,
    IngestionSource,
    Order,
    OrderEvent,
    OrderEventType,
    OrderItem,
    OrderStatus,
)


class WebhookOrderPayload(BaseModel):
    """Shape of one line in `specs/webhook_orders.jsonl` (plan §1)."""

    order_id: str
    order_source: str
    restaurant: str
    first_name: str
    last_name: str
    total: float
    items: list[str]
    notes: str = ""
    update: list[str] | None = None


class WebhookIngestionError(Exception):
    """The payload didn't match the expected webhook shape."""


def ingest_webhook_order(session: Session, raw_payload: dict[str, Any]) -> Order:
    """Upsert one webhook order-creation or cancellation event, per plan §4.1.

    Idempotent by design: redelivering the same `order_id` (a common webhook
    retry behavior) upserts the existing order and appends `ORDER_UPDATED`
    rather than duplicating it. A payload that doesn't match the expected
    shape is rejected (`WebhookIngestionError`) and logged as a failed
    `IngestionRun` rather than silently dropped.
    """
    run = IngestionRun(source=IngestionSource.WEBHOOK, started_at=datetime.now(UTC))

    try:
        payload = WebhookOrderPayload.model_validate(raw_payload)
    except ValidationError as exc:
        _fail_run(session, run, f"malformed webhook payload: {exc}")
        raise WebhookIngestionError(run.message) from exc

    existing = session.exec(
        select(Order).where(
            Order.source == IngestionSource.WEBHOOK,
            Order.external_id == payload.order_id,
        )
    ).first()

    if payload.update is not None:
        order = _apply_cancellation(session, run, existing, payload)
    elif existing is not None:
        order = _apply_update(session, run, existing, payload)
    else:
        order = _create_order(session, run, payload)

    run.finished_at = datetime.now(UTC)
    run.outcome = IngestionRunOutcome.SUCCESS
    session.add(run)
    session.commit()
    session.refresh(order)
    return order


def _create_order(session: Session, run: IngestionRun, payload: WebhookOrderPayload) -> Order:
    order = Order(
        source=IngestionSource.WEBHOOK,
        external_id=payload.order_id,
        status=OrderStatus.RECEIVED,
        delivery_platform=payload.order_source,
        restaurant=payload.restaurant,
        customer_first_name=payload.first_name,
        customer_last_name=payload.last_name,
        notes=payload.notes or None,
        total=payload.total,
    )
    session.add(order)

    for name in payload.items:
        session.add(OrderItem(order_id=order.id, name=name))

    session.add(
        OrderEvent(
            order_id=order.id,
            event_type=OrderEventType.ORDER_RECEIVED,
            source=IngestionSource.WEBHOOK,
            detail={"order_id": payload.order_id},
        )
    )
    run.records_created = 1
    return order


def _apply_update(session: Session, run: IngestionRun, existing: Order, payload: WebhookOrderPayload) -> Order:
    existing.delivery_platform = payload.order_source
    existing.restaurant = payload.restaurant
    existing.customer_first_name = payload.first_name
    existing.customer_last_name = payload.last_name
    existing.notes = payload.notes or None
    existing.total = payload.total
    existing.updated_at = datetime.now(UTC)

    # The payload carries the full current item list, so replace wholesale
    # rather than trying to diff — there's no per-item id to match against.
    for item in list(existing.items):
        session.delete(item)
    for name in payload.items:
        session.add(OrderItem(order_id=existing.id, name=name))

    session.add(existing)
    session.add(
        OrderEvent(
            order_id=existing.id,
            event_type=OrderEventType.ORDER_UPDATED,
            source=IngestionSource.WEBHOOK,
            detail={"order_id": payload.order_id},
        )
    )
    run.records_updated = 1
    return existing


def _apply_cancellation(
    session: Session, run: IngestionRun, existing: Order | None, payload: WebhookOrderPayload
) -> Order:
    if existing is None:
        # Not observed in the sample data (cancellations always follow an
        # earlier creation event there), but the cancellation payload carries
        # every field a creation payload does, so it's still fully ingestable.
        order = _create_order(session, run, payload)
        run.records_created = 1
    else:
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
        order = existing
        run.records_updated = 1

    order.status = OrderStatus.CANCELLED
    session.add(order)
    session.add(
        OrderEvent(
            order_id=order.id,
            event_type=OrderEventType.ORDER_CANCELLED,
            source=IngestionSource.WEBHOOK,
            detail={"order_id": payload.order_id, "update": payload.update},
        )
    )
    return order


def _fail_run(session: Session, run: IngestionRun, message: str) -> None:
    run.finished_at = datetime.now(UTC)
    run.outcome = IngestionRunOutcome.FAILURE
    run.message = message
    session.add(run)
    session.commit()
