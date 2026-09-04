from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import IngestionSource, MealType, Order, OrderEvent, OrderEventType, OrderStatus

NEW_ORDER_PAYLOAD: dict[str, Any] = {
    "order_id": "dispatch-order-1",
    "order_source": "Overeats",
    "restaurant": "Sam & Ella's",
    "first_name": "Laura",
    "last_name": "Kinney",
    "total": 42.5,
    "items": ["Lemon meringue pie", "Cherry pie à la mode"],
    "notes": "",
}


def test_dispatch_transitions_status_and_appends_event() -> None:
    with TestClient(app) as client:
        create = client.post("/ingest/webhook/orders", json=NEW_ORDER_PAYLOAD)
        order_id = create.json()["id"]

        response = client.post(f"/orders/{order_id}/dispatch")

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == order_id
    assert body["source"] == "webhook"
    assert body["restaurant"] == "Sam & Ella's"
    assert {item["name"] for item in body["items"]} == set(NEW_ORDER_PAYLOAD["items"])

    with Session(engine) as session:
        order = session.get(Order, uuid.UUID(order_id))
        assert order is not None
        assert order.status == OrderStatus.DISPATCHED

        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == order.id)).all()
        assert [e.event_type for e in events] == [
            OrderEventType.ORDER_RECEIVED,
            OrderEventType.ORDER_DISPATCHED,
        ]
        assert events[-1].detail["order_id"] == order_id


def test_dispatching_an_already_dispatched_order_is_rejected() -> None:
    with TestClient(app) as client:
        create = client.post("/ingest/webhook/orders", json=NEW_ORDER_PAYLOAD)
        order_id = create.json()["id"]

        first = client.post(f"/orders/{order_id}/dispatch")
        assert first.status_code == 200

        second = client.post(f"/orders/{order_id}/dispatch")

    assert second.status_code == 400
    assert "already dispatched" in second.json()["detail"]


def test_dispatching_a_cancelled_order_is_rejected() -> None:
    with TestClient(app) as client:
        create = client.post("/ingest/webhook/orders", json=NEW_ORDER_PAYLOAD)
        order_id = create.json()["id"]

        cancel = client.post(
            "/ingest/webhook/orders", json={**NEW_ORDER_PAYLOAD, "update": ["cancelled"]}
        )
        assert cancel.status_code == 200

        response = client.post(f"/orders/{order_id}/dispatch")

    assert response.status_code == 400
    assert "cancelled" in response.json()["detail"]


def test_dispatching_an_order_with_no_items_is_rejected() -> None:
    with Session(engine) as session:
        order = Order(source=IngestionSource.CSV_UPLOAD, meal=MealType.LUNCH, for_tomorrow=False)
        session.add(order)
        session.commit()
        order_id = order.id

    with TestClient(app) as client:
        response = client.post(f"/orders/{order_id}/dispatch")

    assert response.status_code == 400
    assert "no items" in response.json()["detail"]


def test_dispatching_a_nonexistent_order_404s() -> None:
    with TestClient(app) as client:
        response = client.post(f"/orders/{uuid.uuid4()}/dispatch")

    assert response.status_code == 404
