from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.ingest import router as ingest_router
from app.api.routes.orders import router as orders_router
from app.api.routes.pages import router as pages_router
from app.config import get_settings
from app.db import init_db
from app.ingestion.polling import PollingBackoff, PollingScheduler

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()

    settings = get_settings()
    scheduler: PollingScheduler | None = None
    if settings.polling_enabled:
        backoff = PollingBackoff(settings.polling_backoff_initial_seconds, settings.polling_backoff_max_seconds)
        scheduler = PollingScheduler(settings.polling_api_base_url, settings.polling_interval_seconds, backoff)
        scheduler.start()

    yield

    if scheduler is not None:
        await scheduler.stop()


app = FastAPI(title="Order Management System", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(orders_router)
app.include_router(ingest_router)
app.include_router(pages_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
