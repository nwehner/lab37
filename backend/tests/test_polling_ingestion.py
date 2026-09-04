from __future__ import annotations

import json
from pathlib import Path

import httpx
from sqlmodel import Session, select

from app.db import engine
from app.ingestion.polling import PollingBackoff, get_last_poll_cursor, poll_once
from app.models import (
    IngestionRun,
    IngestionRunOutcome,
    IngestionSource,
    ItemStatus,
    Order,
    OrderEvent,
    OrderEventType,
    OrderItem,
    OrderStatus,
)
from mock_upstream.app import create_app

SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "specs"


def _mock_client(lines: list[dict[str, object]]) -> httpx.AsyncClient:
    app = create_app(lines)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock-upstream")


async def test_first_poll_ingests_items_creates_orders_and_advances_cursor() -> None:
    lines: list[dict[str, object]] = [
        {
            "response": 200,
            "data": {
                "hash-1": {"order": 1, "name": "Espresso", "category": "drink", "price": 3.5, "status": "ordered"},
                "hash-2": {"order": 1, "name": "Croissant", "category": "food", "price": 4.0, "status": "ordered"},
            },
        }
    ]

    with Session(engine) as session:
        assert get_last_poll_cursor(session) is None

        async with _mock_client(lines) as client:
            run = await poll_once(session, client)

        assert run.outcome == IngestionRunOutcome.SUCCESS
        assert run.records_created == 2
        assert get_last_poll_cursor(session) == run.started_at

        order = session.exec(
            select(Order).where(Order.source == IngestionSource.POLLING_API, Order.external_id == "1")
        ).one()
        assert order.status == OrderStatus.RECEIVED
        assert {item.name for item in order.items} == {"Espresso", "Croissant"}

        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == order.id)).all()
        event_types = [e.event_type for e in events]
        assert event_types.count(OrderEventType.ORDER_RECEIVED) == 1
        assert event_types.count(OrderEventType.ITEM_STATUS_CHANGED) == 2


async def test_reingesting_same_item_hash_is_idempotent_and_updates_status() -> None:
    lines: list[dict[str, object]] = [
        {
            "response": 200,
            "data": {"hash-1": {"order": 1, "name": "Espresso", "category": "drink", "price": 3.5, "status": "ordered"}},
        },
    ]

    with Session(engine) as session:
        async with _mock_client(lines) as client:
            first = await poll_once(session, client)
            assert first.records_created == 1

            await client.post("/reset")
            # Same hash, same status: idempotent no-op, no new event.
            second = await poll_once(session, client)
            assert second.records_created == 0
            assert second.records_updated == 0

    with Session(engine) as session:
        items = session.exec(select(OrderItem).where(OrderItem.external_item_id == "hash-1")).all()
        assert len(items) == 1
        events = session.exec(
            select(OrderEvent).where(OrderEvent.event_type == OrderEventType.ITEM_STATUS_CHANGED)
        ).all()
        assert len(events) == 1


async def test_status_progression_updates_item_and_derives_order_status() -> None:
    ordered_lines: list[dict[str, object]] = [
        {
            "response": 200,
            "data": {
                "hash-1": {"order": 1, "name": "Espresso", "category": "drink", "price": 3.5, "status": "ordered"}
            },
        }
    ]
    processing_lines: list[dict[str, object]] = [
        {
            "response": 200,
            "data": {
                "hash-1": {"order": 1, "name": "Espresso", "category": "drink", "price": 3.5, "status": "processing"}
            },
        }
    ]

    with Session(engine) as session:
        async with _mock_client(ordered_lines) as client:
            await poll_once(session, client)
        async with _mock_client(processing_lines) as client:
            run = await poll_once(session, client)

        assert run.records_updated == 1

        order = session.exec(
            select(Order).where(Order.source == IngestionSource.POLLING_API, Order.external_id == "1")
        ).one()
        assert order.status == OrderStatus.IN_PREP
        assert order.items[0].status == ItemStatus.PROCESSING

        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == order.id)).all()
        change_events = [e for e in events if e.event_type == OrderEventType.ITEM_STATUS_CHANGED]
        assert change_events[-1].detail == {
            "external_item_id": "hash-1",
            "old_status": "ordered",
            "new_status": "processing",
        }


async def test_response_500_with_no_data_fails_and_does_not_advance_cursor() -> None:
    lines: list[dict[str, object]] = [{"response": 500, "error": "upstream exploded"}]

    with Session(engine) as session:
        async with _mock_client(lines) as client:
            run = await poll_once(session, client)

        assert run.outcome == IngestionRunOutcome.FAILURE
        assert get_last_poll_cursor(session) is None

        orders = session.exec(select(Order).where(Order.source == IngestionSource.POLLING_API)).all()
        assert orders == []


async def test_response_500_with_partial_data_ingests_and_advances_cursor() -> None:
    lines: list[dict[str, object]] = [
        {
            "response": 500,
            "error": "upstream degraded; partial data may be present",
            "data": {"hash-1": {"order": 1, "name": "Espresso", "category": "drink", "price": 3.5, "status": "ordered"}},
        }
    ]

    with Session(engine) as session:
        async with _mock_client(lines) as client:
            run = await poll_once(session, client)

        assert run.outcome == IngestionRunOutcome.PARTIAL
        assert run.records_created == 1
        assert get_last_poll_cursor(session) == run.started_at
        assert run.message is not None and "partial data" in run.message


def test_backoff_grows_on_failure_and_resets_on_success() -> None:
    backoff = PollingBackoff(initial_seconds=5.0, max_seconds=40.0)

    assert backoff.record_failure() == 5.0
    assert backoff.record_failure() == 10.0
    assert backoff.record_failure() == 20.0
    assert backoff.record_failure() == 40.0
    assert backoff.record_failure() == 40.0  # capped

    backoff.record_success()
    assert backoff.current_seconds == 5.0


async def test_full_real_upstream_corpus_reports_expected_outcome_counts() -> None:
    lines = [json.loads(line) for line in (SPECS_DIR / "api_responses.jsonl").read_text().splitlines() if line.strip()]
    expected_success = sum(1 for line in lines if line["response"] == 200)
    expected_partial = sum(1 for line in lines if line["response"] == 500 and line.get("data"))
    expected_failure = sum(1 for line in lines if line["response"] == 500 and not line.get("data"))

    outcomes: list[IngestionRunOutcome] = []
    with Session(engine) as session:
        async with _mock_client(lines) as client:
            for _ in range(len(lines)):
                outcomes.append((await poll_once(session, client)).outcome)

    assert outcomes.count(IngestionRunOutcome.SUCCESS) == expected_success
    assert outcomes.count(IngestionRunOutcome.PARTIAL) == expected_partial
    assert outcomes.count(IngestionRunOutcome.FAILURE) == expected_failure

    with Session(engine) as session:
        runs = session.exec(select(IngestionRun).where(IngestionRun.source == IngestionSource.POLLING_API)).all()
        assert len(runs) == len(lines)

        orders = session.exec(select(Order).where(Order.source == IngestionSource.POLLING_API)).all()
        distinct_order_ids = {str(item["order"]) for line in lines for item in (line.get("data") or {}).values()}
        assert {o.external_id for o in orders} == distinct_order_ids
