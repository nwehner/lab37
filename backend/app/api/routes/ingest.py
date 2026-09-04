from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel import Session

from app.api.schemas import CsvUploadSummary, IngestionRunListResponse, IngestionRunRead, OrderRead
from app.config import get_settings
from app.db import get_session
from app.ingestion.csv_upload import CsvIngestionError, ingest_csv_upload
from app.ingestion.polling import poll_once
from app.ingestion.webhook import WebhookIngestionError, ingest_webhook_order
from app.services import queries

router = APIRouter(tags=["ingestion"])


@router.post("/ingest/webhook/orders")
async def receive_webhook_order(
    payload: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
) -> OrderRead:
    try:
        order = ingest_webhook_order(session, payload)
    except WebhookIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OrderRead.model_validate(order)


@router.post("/ingest/poll/trigger")
async def trigger_poll(session: Annotated[Session, Depends(get_session)]) -> IngestionRunRead:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.polling_api_base_url, timeout=10.0) as client:
        run = await poll_once(session, client)
    return IngestionRunRead.model_validate(run)


@router.post("/ingest/csv")
async def upload_csv(
    file: UploadFile,
    session: Annotated[Session, Depends(get_session)],
) -> CsvUploadSummary:
    content = await file.read()
    filename = file.filename or "upload.csv"
    try:
        return ingest_csv_upload(session, filename, content)
    except CsvIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/ingestion/runs")
def list_ingestion_runs(
    session: Annotated[Session, Depends(get_session)],
    offset: int = 0,
    limit: int = 50,
) -> IngestionRunListResponse:
    runs, total = queries.list_ingestion_runs(session, offset=offset, limit=limit)
    return IngestionRunListResponse(
        items=[IngestionRunRead.model_validate(run) for run in runs],
        total=total,
        offset=offset,
        limit=limit,
    )
