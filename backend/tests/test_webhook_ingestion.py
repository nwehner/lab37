from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import (
    IngestionRun,
    IngestionRunOutcome,
    IngestionSource,
    Order,
    OrderEvent,
    OrderEventType,
    OrderStatus,
)

SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "specs"

NEW_ORDER_PAYLOAD: dict[str, Any] = {
    "order_id": "test-order-1",
    "order_source": "Overeats",
    "restaurant": "Sam & Ella's",
    "first_name": "Laura",
    "last_name": "Kinney",
    "total": 42.5,
    "items": ["Lemon meringue pie", "Cherry pie à la mode"],
    "notes": "",
}


def test_new_order_is_created_with_items_and_received_event() -> None:
    with TestClient(app) as client:
        response = client.post("/ingest/webhook/orders", json=NEW_ORDER_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "webhook"
    assert body["external_id"] == "test-order-1"
    assert body["status"] == "received"
    assert {item["name"] for item in body["items"]} == set(NEW_ORDER_PAYLOAD["items"])

    with Session(engine) as session:
        order = session.exec(
            select(Order).where(Order.source == IngestionSource.WEBHOOK, Order.external_id == "test-order-1")
        ).one()
        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == order.id)).all()
        assert [e.event_type for e in events] == [OrderEventType.ORDER_RECEIVED]

        runs = session.exec(select(IngestionRun).where(IngestionRun.source == IngestionSource.WEBHOOK)).all()
        assert len(runs) == 1
        assert runs[0].outcome == IngestionRunOutcome.SUCCESS
        assert runs[0].records_created == 1


def test_redelivering_the_same_order_id_upserts_instead_of_duplicating() -> None:
    with TestClient(app) as client:
        first = client.post("/ingest/webhook/orders", json=NEW_ORDER_PAYLOAD)
        assert first.status_code == 200

        updated_payload = {**NEW_ORDER_PAYLOAD, "total": 99.99, "items": ["Espresso"]}
        second = client.post("/ingest/webhook/orders", json=updated_payload)
        assert second.status_code == 200

    with Session(engine) as session:
        orders = session.exec(
            select(Order).where(Order.source == IngestionSource.WEBHOOK, Order.external_id == "test-order-1")
        ).all()
        assert len(orders) == 1
        assert orders[0].total == 99.99
        assert [item.name for item in orders[0].items] == ["Espresso"]

        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == orders[0].id)).all()
        assert [e.event_type for e in events] == [
            OrderEventType.ORDER_RECEIVED,
            OrderEventType.ORDER_UPDATED,
        ]


def test_cancellation_event_marks_existing_order_cancelled() -> None:
    with TestClient(app) as client:
        client.post("/ingest/webhook/orders", json=NEW_ORDER_PAYLOAD)

        cancel_payload = {**NEW_ORDER_PAYLOAD, "update": ["cancelled"]}
        response = client.post("/ingest/webhook/orders", json=cancel_payload)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    with Session(engine) as session:
        order = session.exec(
            select(Order).where(Order.source == IngestionSource.WEBHOOK, Order.external_id == "test-order-1")
        ).one()
        assert order.status == OrderStatus.CANCELLED

        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == order.id)).all()
        assert [e.event_type for e in events] == [
            OrderEventType.ORDER_RECEIVED,
            OrderEventType.ORDER_CANCELLED,
        ]


def test_cancellation_of_never_seen_order_id_still_ingests_it_as_cancelled() -> None:
    """Not present in the sample corpus, but the cancellation payload carries every
    field a creation payload does, so per plan §4.1/Phase 3 it's still fully ingestible
    rather than rejected for referencing an unknown order_id."""
    cancel_payload = {**NEW_ORDER_PAYLOAD, "order_id": "never-seen-order", "update": ["cancelled"]}

    with TestClient(app) as client:
        response = client.post("/ingest/webhook/orders", json=cancel_payload)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    with Session(engine) as session:
        order = session.exec(
            select(Order).where(Order.source == IngestionSource.WEBHOOK, Order.external_id == "never-seen-order")
        ).one()
        assert order.status == OrderStatus.CANCELLED
        assert {item.name for item in order.items} == set(NEW_ORDER_PAYLOAD["items"])

        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == order.id)).all()
        assert [e.event_type for e in events] == [
            OrderEventType.ORDER_RECEIVED,
            OrderEventType.ORDER_CANCELLED,
        ]


def test_malformed_payload_is_rejected_and_logged_as_failed_run() -> None:
    bad_payload = {"order_id": "missing-fields-order"}

    with TestClient(app) as client:
        response = client.post("/ingest/webhook/orders", json=bad_payload)

    assert response.status_code == 400

    with Session(engine) as session:
        orders = session.exec(select(Order).where(Order.external_id == "missing-fields-order")).all()
        assert orders == []

        runs = session.exec(select(IngestionRun).where(IngestionRun.source == IngestionSource.WEBHOOK)).all()
        assert len(runs) == 1
        assert runs[0].outcome == IngestionRunOutcome.FAILURE
        assert runs[0].message is not None


def test_real_webhook_corpus_ingests_and_resolves_known_cancellations() -> None:
    lines = [line for line in (SPECS_DIR / "webhook_orders.jsonl").read_text().splitlines() if line.strip()]
    payloads = [json.loads(line) for line in lines]
    cancelled_ids = {p["order_id"] for p in payloads if "update" in p}
    unique_ids = {p["order_id"] for p in payloads}

    with TestClient(app) as client:
        for payload in payloads:
            response = client.post("/ingest/webhook/orders", json=payload)
            assert response.status_code == 200, response.text

    with Session(engine) as session:
        orders = session.exec(select(Order).where(Order.source == IngestionSource.WEBHOOK)).all()
        assert len(orders) == len(unique_ids)

        cancelled = {o.external_id for o in orders if o.status == OrderStatus.CANCELLED}
        assert cancelled == cancelled_ids
