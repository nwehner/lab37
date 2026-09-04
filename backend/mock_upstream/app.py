"""Mock polling upstream that replays `specs/api_responses.jsonl`, one line
per call, per plan §8.

This lets the real polling client (`app/ingestion/polling.py`) exercise
actual HTTP request/response handling — including the real `response: 500`
lines, some with usable partial `data` and some without — instead of a
stubbed bypass. Each line's own `response` field becomes the real HTTP
status code of the reply, since that's the field the polling client's
fault-tolerance logic (plan §3) actually branches on.

Run standalone:
    uv run uvicorn mock_upstream.app:app --port 8001
Then point the real app at it:
    ORDER_MGMT_POLLING_API_BASE_URL=http://localhost:8001 uv run uvicorn app.main:app
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BACKEND_DIR.parent / "specs" / "api_responses.jsonl"


def load_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class MockUpstreamState:
    """Sequential, in-memory cursor over the replayed lines."""

    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self.lines = lines
        self.index = 0

    def next_line(self) -> dict[str, Any] | None:
        if self.index >= len(self.lines):
            return None
        line = self.lines[self.index]
        self.index += 1
        return line

    def reset(self) -> None:
        self.index = 0


def create_app(lines: list[dict[str, Any]] | None = None) -> FastAPI:
    state = MockUpstreamState(lines if lines is not None else load_lines(DEFAULT_FILE))
    mock_app = FastAPI(title="Mock Polling Upstream")

    @mock_app.get("/poll")
    def poll(time_since: str | None = None) -> JSONResponse:
        line = state.next_line()
        if line is None:
            # Cursor has caught up to the end of the replayed corpus: report
            # a normal, empty poll rather than an error.
            return JSONResponse({"response": 200, "data": {}})
        return JSONResponse(line, status_code=line["response"])

    @mock_app.post("/reset")
    def reset() -> dict[str, str]:
        state.reset()
        return {"status": "reset"}

    return mock_app


app = create_app()
