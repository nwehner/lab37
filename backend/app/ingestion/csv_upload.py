from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from sqlmodel import Session

from app.api.schemas import CsvUploadSummary
from app.ingestion.csv_item_parser import load_known_items, parse_items_field
from app.models import (
    IngestionRun,
    IngestionRunOutcome,
    IngestionSource,
    MealType,
    Order,
    OrderEvent,
    OrderEventType,
    OrderItem,
    OrderStatus,
)

_TOMORROW_VALUES = {"true": True, "false": False}


class CsvIngestionError(Exception):
    """The uploaded file itself could not be read as CSV at all (not a per-row issue)."""


def ingest_csv_upload(session: Session, filename: str, content: bytes) -> CsvUploadSummary:
    """Parse and persist one uploaded CSV file, per plan §4.3.

    Per-row parsing is non-fatal (§3): a row with an unrecognized `items` token,
    `meal`, or `tomorrow` value still produces an `Order` (raw text preserved) plus an
    `INGESTION_WARNING` event, rather than aborting the whole file. Only a file that
    can't be decoded or lacks the expected columns raises `CsvIngestionError`.
    """
    run = IngestionRun(source=IngestionSource.CSV_UPLOAD, started_at=datetime.now(UTC))

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        _fail_run(session, run, f"could not decode file as UTF-8: {exc}")
        raise CsvIngestionError(run.message) from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "items" not in reader.fieldnames:
        _fail_run(session, run, f"missing required 'items' column; found columns {reader.fieldnames}")
        raise CsvIngestionError(run.message)

    known_items = load_known_items()
    rows_ingested = 0
    rows_with_warnings = 0
    warnings_count = 0

    for row_number, row in enumerate(reader, start=1):
        rows_ingested += 1
        row_had_warning = False

        meal, meal_unrecognized = _parse_meal(row.get("meal"))
        for_tomorrow, tomorrow_unrecognized = _parse_tomorrow(row.get("tomorrow"))

        order = Order(
            source=IngestionSource.CSV_UPLOAD,
            status=OrderStatus.RECEIVED,
            customer_first_name=row.get("first_name") or None,
            customer_last_name=row.get("last_name") or None,
            notes=row.get("notes") or None,
            meal=meal,
            for_tomorrow=for_tomorrow,
        )
        session.add(order)

        session.add(
            OrderEvent(
                order_id=order.id,
                event_type=OrderEventType.ORDER_RECEIVED,
                source=IngestionSource.CSV_UPLOAD,
                detail={"filename": filename, "row": row_number},
            )
        )

        for item in parse_items_field(row.get("items", ""), known_items):
            session.add(OrderItem(order_id=order.id, name=item.name))
            if not item.matched:
                row_had_warning = True
                warnings_count += 1
                session.add(
                    OrderEvent(
                        order_id=order.id,
                        event_type=OrderEventType.INGESTION_WARNING,
                        source=IngestionSource.CSV_UPLOAD,
                        detail={
                            "reason": "unmatched_item_text",
                            "raw_items_field": row.get("items", ""),
                            "unmatched_text": item.name,
                        },
                    )
                )

        if meal_unrecognized:
            row_had_warning = True
            warnings_count += 1
            session.add(
                OrderEvent(
                    order_id=order.id,
                    event_type=OrderEventType.INGESTION_WARNING,
                    source=IngestionSource.CSV_UPLOAD,
                    detail={"reason": "unrecognized_meal_value", "raw_value": row.get("meal")},
                )
            )

        if tomorrow_unrecognized:
            row_had_warning = True
            warnings_count += 1
            session.add(
                OrderEvent(
                    order_id=order.id,
                    event_type=OrderEventType.INGESTION_WARNING,
                    source=IngestionSource.CSV_UPLOAD,
                    detail={"reason": "unrecognized_tomorrow_value", "raw_value": row.get("tomorrow")},
                )
            )

        if row_had_warning:
            rows_with_warnings += 1

    run.finished_at = datetime.now(UTC)
    run.records_created = rows_ingested
    run.warnings_count = warnings_count
    run.outcome = IngestionRunOutcome.SUCCESS if warnings_count == 0 else IngestionRunOutcome.PARTIAL
    session.add(run)
    session.commit()

    return CsvUploadSummary(filename=filename, rows_ingested=rows_ingested, rows_with_warnings=rows_with_warnings)


def _fail_run(session: Session, run: IngestionRun, message: str) -> None:
    run.finished_at = datetime.now(UTC)
    run.outcome = IngestionRunOutcome.FAILURE
    run.message = message
    session.add(run)
    session.commit()


def _parse_meal(raw: str | None) -> tuple[MealType | None, bool]:
    if raw is None or raw.strip() == "":
        return None, False
    try:
        return MealType(raw.strip().lower()), False
    except ValueError:
        return None, True


def _parse_tomorrow(raw: str | None) -> tuple[bool | None, bool]:
    if raw is None or raw.strip() == "":
        return None, False
    value = _TOMORROW_VALUES.get(raw.strip().lower())
    if value is None:
        return None, True
    return value, False
