from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["pages"], include_in_schema=False)


@router.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "upload.html")
