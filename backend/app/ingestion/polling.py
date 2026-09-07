"""Polling-API ingestion pipeline, per plan §4.2 and the fault-tolerance
strategy in §3.

The client tracks its own `time_since` cursor — the upstream payload has no
timestamps at all (plan §1), so this is bookkeeping we own, not something we
get back. The cursor only advances past a poll whose `response == 200`, or a
`500` that still carried usable `data` (tagged `PARTIAL`, per §3). A `500`
with no usable data leaves the cursor where it was, so the same window is
re-requested on the next attempt. Because item hash ids are stable across
polls, re-ingesting an overlapping window is naturally idempotent.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlmodel import Session, col, select

from app.db import engine
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

# Item statuses that mean "past ordered, not yet delivered" — used to derive
# the parent Order's status (§2: OrderStatus.IN_PREP is "derived from polling
# item statuses, when applicable").
_IN_PREP_STATUSES = {ItemStatus.PROCESSING, ItemStatus.WITH_COURIER}
# Terminal per-item outcomes: nothing further happens to an item once it's here.
_TERMINAL_STATUSES = {ItemStatus.DELIVERED, ItemStatus.CANCELLED}
_DERIVABLE_ORDER_STATUSES = {OrderStatus.RECEIVED, OrderStatus.IN_PREP, OrderStatus.DELIVERED}


class PollingBackoff:
    """In-process capped-exponential backoff state for the poll loop.

    Not persisted: per plan §13, the polling scheduler runs in-process at
    prototype scale, and backoff timing is only meaningful within one
    running process's own retry loop.
    """

    def __init__(self, initial_seconds: float, max_seconds: float) -> None:
        self.initial_seconds = initial_seconds
        self.max_seconds = max_seconds
        self.current_seconds = initial_seconds

    def record_success(self) -> None:
        self.current_seconds = self.initial_seconds

    def record_failure(self) -> float:
        wait = self.current_seconds
        self.current_seconds = min(self.current_seconds * 2, self.max_seconds)
        return wait


def get_last_poll_cursor(session: Session) -> datetime | None:
    """The `time_since` cursor: the start time of the most recent poll run
    that advanced (SUCCESS or PARTIAL), or None before the first poll."""
    run = session.exec(
        select(IngestionRun)
        .where(
            IngestionRun.source == IngestionSource.POLLING_API,
            col(IngestionRun.outcome).in_([IngestionRunOutcome.SUCCESS, IngestionRunOutcome.PARTIAL]),
        )
        .order_by(col(IngestionRun.started_at).desc())
    ).first()
    return run.started_at if run else None


async def poll_once(session: Session, client: httpx.AsyncClient) -> IngestionRun:
    """Perform one poll cycle against `client` and persist the outcome.

    `client` is an injected `httpx.AsyncClient` rather than a hardcoded URL
    so tests can point it at an in-process mock ASGI app (plan §8) via
    `httpx.ASGITransport` instead of a live server, while still exercising
    real HTTP request/response handling.
    """
    run = IngestionRun(source=IngestionSource.POLLING_API, started_at=datetime.now(UTC))
    cursor = get_last_poll_cursor(session)
    params = {"time_since": cursor.isoformat()} if cursor else {}

    try:
        response = await client.get("/poll", params=params)
    except httpx.HTTPError as exc:
        _finish(session, run, IngestionRunOutcome.FAILURE, message=f"upstream request failed: {exc}")
        return run

    try:
        body = response.json()
    except ValueError:
        _finish(
            session,
            run,
            IngestionRunOutcome.FAILURE,
            message=f"upstream returned non-JSON body (status {response.status_code})",
        )
        return run

    data: dict[str, Any] = body.get("data") or {}
    error = body.get("error")

    if response.status_code == 200:
        created, updated = _ingest_items(session, data)
        _finish(session, run, IngestionRunOutcome.SUCCESS, records_created=created, records_updated=updated)
    elif data:
        # A 500 that still carries usable data (plan §1, §3) — ingest what's there.
        created, updated = _ingest_items(session, data)
        _finish(
            session,
            run,
            IngestionRunOutcome.PARTIAL,
            records_created=created,
            records_updated=updated,
            message=f"upstream returned {response.status_code} with partial data: {error}",
        )
    else:
        _finish(
            session,
            run,
            IngestionRunOutcome.FAILURE,
            message=f"upstream returned {response.status_code} with no usable data: {error}",
        )

    return run


def _ingest_items(session: Session, data: dict[str, Any]) -> tuple[int, int]:
    created = 0
    updated = 0
    touched_orders: set[uuid.UUID] = set()

    for external_item_id, payload in data.items():
        order_external_id = str(payload["order"])
        status = ItemStatus(payload["status"])

        order = session.exec(
            select(Order).where(
                Order.source == IngestionSource.POLLING_API,
                Order.external_id == order_external_id,
            )
        ).first()
        if order is None:
            order = Order(
                source=IngestionSource.POLLING_API,
                external_id=order_external_id,
                status=OrderStatus.RECEIVED,
            )
            session.add(order)
            session.add(
                OrderEvent(
                    order_id=order.id,
                    event_type=OrderEventType.ORDER_RECEIVED,
                    source=IngestionSource.POLLING_API,
                    detail={"order": order_external_id},
                )
            )

        item = session.exec(select(OrderItem).where(OrderItem.external_item_id == external_item_id)).first()

        if item is None:
            session.add(
                OrderItem(
                    order_id=order.id,
                    external_item_id=external_item_id,
                    name=payload["name"],
                    category=payload.get("category"),
                    price=payload.get("price"),
                    status=status,
                )
            )
            session.add(
                OrderEvent(
                    order_id=order.id,
                    event_type=OrderEventType.ITEM_STATUS_CHANGED,
                    source=IngestionSource.POLLING_API,
                    detail={"external_item_id": external_item_id, "old_status": None, "new_status": status.value},
                )
            )
            created += 1
        elif item.status != status:
            old_status = item.status
            item.name = payload["name"]
            item.category = payload.get("category")
            item.price = payload.get("price")
            item.status = status
            session.add(item)
            session.add(
                OrderEvent(
                    order_id=order.id,
                    event_type=OrderEventType.ITEM_STATUS_CHANGED,
                    source=IngestionSource.POLLING_API,
                    detail={
                        "external_item_id": external_item_id,
                        "old_status": old_status.value if old_status else None,
                        "new_status": status.value,
                    },
                )
            )
            updated += 1

        touched_orders.add(order.id)

    session.flush()
    for order_id in touched_orders:
        _derive_order_status(session, order_id)

    return created, updated


def _derive_order_status(session: Session, order_id: uuid.UUID) -> None:
    """Derive `order.status` from its items' polled statuses.

    Cancellation isn't observed anywhere in the sample `api_responses.jsonl`
    corpus (no line ever carries `status: "cancelled"`), but the spec states
    the polling API "may return... cancellations", and the item-status feed
    is the only channel this API shape has to carry one. We treat
    `ItemStatus.CANCELLED` the same way an item reaching `DELIVERED` is
    treated: a terminal per-item outcome. An order whose items are *all*
    cancelled is itself cancelled (and gets an explicit `ORDER_CANCELLED`
    event, mirroring the webhook pipeline, so it shows up in the order's
    history — not just a silent status flip). An order with a mix of
    cancelled and delivered items (nothing left pending) is treated as
    resolved/`DELIVERED` rather than cancelled, since some of what was
    ordered did go out.
    """
    order = session.get(Order, order_id)
    if order is None or order.status not in _DERIVABLE_ORDER_STATUSES:
        return  # never override a manually dispatched order, or one already resolved by an earlier derivation

    statuses = [item.status for item in order.items if item.status is not None]
    if not statuses:
        return

    if all(s == ItemStatus.CANCELLED for s in statuses):
        new_status = OrderStatus.CANCELLED
    elif all(s in _TERMINAL_STATUSES for s in statuses):
        new_status = OrderStatus.DELIVERED
    elif any(s in _IN_PREP_STATUSES or s == ItemStatus.DELIVERED for s in statuses):
        new_status = OrderStatus.IN_PREP
    else:
        new_status = OrderStatus.RECEIVED

    if new_status != order.status:
        order.status = new_status
        order.updated_at = datetime.now(UTC)
        session.add(order)
        if new_status == OrderStatus.CANCELLED:
            session.add(
                OrderEvent(
                    order_id=order.id,
                    event_type=OrderEventType.ORDER_CANCELLED,
                    source=IngestionSource.POLLING_API,
                    detail={"reason": "all items reported cancelled via polling"},
                )
            )


def _finish(
    session: Session,
    run: IngestionRun,
    outcome: IngestionRunOutcome,
    *,
    records_created: int = 0,
    records_updated: int = 0,
    message: str | None = None,
) -> None:
    run.finished_at = datetime.now(UTC)
    run.outcome = outcome
    run.records_created = records_created
    run.records_updated = records_updated
    run.message = message
    session.add(run)
    session.commit()


async def _run_one_poll(base_url: str) -> IngestionRun:
    with Session(engine) as session:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            return await poll_once(session, client)


class PollingScheduler:
    """In-process interval scheduler for the polling pipeline (plan §4.2).

    Runs as a background asyncio task for the lifetime of the app (§13:
    an in-process scheduler is fine at prototype scale; a real scheduler
    like Celery beat or cron is the documented upgrade path). On failure it
    waits out the current backoff instead of the regular interval before
    retrying; a success resets the backoff and returns to the normal
    interval.
    """

    def __init__(self, base_url: str, interval_seconds: float, backoff: PollingBackoff) -> None:
        self.base_url = base_url
        self.interval_seconds = interval_seconds
        self.backoff = backoff
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            try:
                run = await _run_one_poll(self.base_url)
            except Exception:  # noqa: BLE001 - the loop must survive any single failed attempt
                wait = self.backoff.record_failure()
            else:
                if run.outcome == IngestionRunOutcome.FAILURE:
                    wait = self.backoff.record_failure()
                else:
                    self.backoff.record_success()
                    wait = self.interval_seconds
            await asyncio.sleep(wait)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
