from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.schemas import IngestionRunRead, OrderEventRead, OrderRead
from app.db import get_session
from app.models import IngestionSource, MealType, OrderStatus
from app.services import queries
from app.web import templates

router = APIRouter(tags=["pages"], include_in_schema=False)

DASHBOARD_PAGE_SIZE = 50
RECENT_RUNS_LIMIT = 10


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    source: IngestionSource | None = None,
    order_status: OrderStatus | None = None,
    restaurant: str | None = None,
    meal: MealType | None = None,
    offset: int = 0,
) -> HTMLResponse:
    orders, total = queries.list_orders(
        session,
        source=source,
        order_status=order_status,
        restaurant=restaurant,
        meal=meal,
        offset=offset,
        limit=DASHBOARD_PAGE_SIZE,
    )
    runs, _ = queries.list_ingestion_runs(session, offset=0, limit=RECENT_RUNS_LIMIT)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "orders": [OrderRead.model_validate(order) for order in orders],
            "runs": [IngestionRunRead.model_validate(run) for run in runs],
            "total": total,
            "offset": offset,
            "limit": DASHBOARD_PAGE_SIZE,
            "filters": {
                "source": source,
                "order_status": order_status,
                "restaurant": restaurant,
                "meal": meal,
            },
            "sources": list(IngestionSource),
            "statuses": list(OrderStatus),
            "meals": list(MealType),
            "restaurants": queries.list_distinct_restaurants(session),
        },
    )


@router.get("/orders/{order_id}/view", response_class=HTMLResponse)
def order_detail_page(
    order_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    order = queries.get_order_by_id(session, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    events = queries.list_order_events(session, order_id)

    return templates.TemplateResponse(
        request,
        "order_detail.html",
        {
            "order": OrderRead.model_validate(order),
            "events": [OrderEventRead.model_validate(event) for event in events],
        },
    )


@router.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "upload.html")
