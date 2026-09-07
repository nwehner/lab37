from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import engine
from app.ingestion.polling import poll_once
from app.main import app
from mock_upstream.app import create_app

ORDER_PAYLOAD: dict[str, Any] = {
    "order_id": "orders-api-test-1",
    "order_source": "Overeats",
    "restaurant": "Sam & Ella's",
    "first_name": "Jessica",
    "last_name": "Jones",
    "total": 18.0,
    "items": ["Fried banana", "Sweet tea"],
    "notes": "extra napkins",
}

OTHER_ORDER_PAYLOAD: dict[str, Any] = {
    "order_id": "orders-api-test-2",
    "order_source": "DoorDrop",
    "restaurant": "Griddle & Co",
    "first_name": "Luke",
    "last_name": "Cage",
    "total": 25.0,
    "items": ["Multigrain sandwich loaf"],
    "notes": "",
}


def test_list_orders_empty_returns_empty_list() -> None:
    with TestClient(app) as client:
        response = client.get("/orders")
    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "offset": 0, "limit": 50}


def test_list_orders_after_ingestion() -> None:
    with TestClient(app) as client:
        client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD)
        client.post("/ingest/webhook/orders", json=OTHER_ORDER_PAYLOAD)

        response = client.get("/orders")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    names = {item["customer_first_name"] for item in body["items"]}
    assert names == {"Jessica", "Luke"}


def test_list_orders_filters_by_source_and_status() -> None:
    with TestClient(app) as client:
        client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD)
        client.post("/ingest/webhook/orders", json=OTHER_ORDER_PAYLOAD)

        matching = client.get("/orders", params={"restaurant": "Sam & Ella's"})
        empty = client.get("/orders", params={"order_status": "delivered"})

    assert matching.status_code == 200
    assert matching.json()["total"] == 1
    assert matching.json()["items"][0]["customer_first_name"] == "Jessica"

    assert empty.status_code == 200
    assert empty.json()["total"] == 0


async def test_polling_cancelled_order_is_surfaced_via_orders_api() -> None:
    poll_lines: list[dict[str, object]] = [
        {
            "response": 200,
            "data": {"hash-1": {"order": 1, "name": "Espresso", "category": "drink", "price": 3.5, "status": "cancelled"}},
        }
    ]
    mock_app = create_app(poll_lines)

    with Session(engine) as session:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app), base_url="http://mock-upstream"
        ) as client:
            await poll_once(session, client)

    with TestClient(app) as client:
        listing = client.get("/orders", params={"order_status": "cancelled"})
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        order_id = listing.json()["items"][0]["id"]

        detail = client.get(f"/orders/{order_id}")
        assert detail.json()["status"] == "cancelled"

        events = client.get(f"/orders/{order_id}/events").json()
        assert [e["event_type"] for e in events] == ["order_received", "item_status_changed", "order_cancelled"]


def test_get_order_returns_json_by_default() -> None:
    with TestClient(app) as client:
        created = client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD).json()
        response = client.get(f"/orders/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert len(body["items"]) == 2


def test_get_order_404_for_unknown_id() -> None:
    with TestClient(app) as client:
        response = client.get(f"/orders/{uuid.uuid4()}")
    assert response.status_code == 404


def test_order_detail_page_renders_html() -> None:
    with TestClient(app) as client:
        created = client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD).json()
        response = client.get(f"/orders/{created['id']}/view")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Jessica" in response.text
    assert "Fried banana" in response.text


def test_order_detail_page_404_for_unknown_id() -> None:
    with TestClient(app) as client:
        response = client.get(f"/orders/{uuid.uuid4()}/view")
    assert response.status_code == 404


def test_get_order_events_returns_timeline() -> None:
    with TestClient(app) as client:
        created = client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD).json()
        client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD)  # redelivery -> ORDER_UPDATED

        response = client.get(f"/orders/{created['id']}/events")

    assert response.status_code == 200
    events = response.json()
    assert [e["event_type"] for e in events] == ["order_received", "order_updated"]


def test_get_order_events_404_for_unknown_id() -> None:
    with TestClient(app) as client:
        response = client.get(f"/orders/{uuid.uuid4()}/events")
    assert response.status_code == 404


def test_dashboard_page_renders_orders() -> None:
    with TestClient(app) as client:
        client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD)
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Jessica" in response.text
    assert "Sam &amp; Ella&#39;s" in response.text or "Sam & Ella's" in response.text


def test_ingestion_runs_endpoint_lists_recent_runs() -> None:
    with TestClient(app) as client:
        client.post("/ingest/webhook/orders", json=ORDER_PAYLOAD)
        response = client.get("/ingestion/runs")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["items"][0]["source"] == "webhook"
