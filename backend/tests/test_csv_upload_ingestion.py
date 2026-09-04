from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import IngestionRun, IngestionRunOutcome, IngestionSource, Order, OrderEvent, OrderEventType

SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "specs"


def test_upload_real_orders_4_csv_has_no_warnings() -> None:
    content = (SPECS_DIR / "orders_4.csv").read_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/ingest/csv",
            files={"file": ("orders_4.csv", content, "text/csv")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "orders_4.csv"
    assert body["rows_ingested"] > 0
    assert body["rows_with_warnings"] == 0

    with Session(engine) as session:
        orders = session.exec(select(Order).where(Order.source == IngestionSource.CSV_UPLOAD)).all()
        assert len(orders) == body["rows_ingested"]

        runs = session.exec(select(IngestionRun).where(IngestionRun.source == IngestionSource.CSV_UPLOAD)).all()
        assert len(runs) == 1
        assert runs[0].outcome == IngestionRunOutcome.SUCCESS
        assert runs[0].records_created == body["rows_ingested"]

        first_order = orders[0]
        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == first_order.id)).all()
        assert any(e.event_type == OrderEventType.ORDER_RECEIVED for e in events)


def test_upload_row_with_unmatched_item_produces_warning_but_still_ingests() -> None:
    csv_content = (
        b"first_name,last_name,items,notes,tomorrow,meal\n"
        b"Ada,Lovelace,\"Espresso, Some Totally Unknown Dish\",,true,breakfast\n"
    )

    with TestClient(app) as client:
        response = client.post(
            "/ingest/csv",
            files={"file": ("edge_case.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["rows_ingested"] == 1
    assert body["rows_with_warnings"] == 1

    with Session(engine) as session:
        order = session.exec(
            select(Order).where(
                Order.source == IngestionSource.CSV_UPLOAD,
                Order.customer_first_name == "Ada",
            )
        ).one()
        events = session.exec(select(OrderEvent).where(OrderEvent.order_id == order.id)).all()
        warning_events = [e for e in events if e.event_type == OrderEventType.INGESTION_WARNING]
        assert len(warning_events) == 1
        assert warning_events[0].detail["unmatched_text"] == "Some Totally Unknown Dish"


def test_upload_rejects_file_missing_items_column() -> None:
    csv_content = b"first_name,last_name\nAda,Lovelace\n"

    with TestClient(app) as client:
        response = client.post(
            "/ingest/csv",
            files={"file": ("bad.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400
