from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.ingest import router as ingest_router
from app.api.routes.orders import router as orders_router
from app.api.routes.pages import router as pages_router
from app.db import init_db

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


app = FastAPI(title="Order Management System", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(orders_router)
app.include_router(ingest_router)
app.include_router(pages_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
