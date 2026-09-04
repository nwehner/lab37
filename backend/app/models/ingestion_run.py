from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.models.enums import IngestionRunOutcome, IngestionSource


class IngestionRun(SQLModel, table=True):
    """A record of one ingestion attempt (webhook delivery, poll cycle, or CSV upload).

    Written for every attempt, not just failures, so the ingestion-activity panel
    (plan §7) has real data and fault patterns are visible without log-diving (§3).
    """

    __tablename__ = "ingestion_run"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source: IngestionSource = Field(index=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    finished_at: datetime | None = None
    outcome: IngestionRunOutcome = IngestionRunOutcome.SUCCESS
    records_created: int = 0
    records_updated: int = 0
    warnings_count: int = 0
    message: str | None = None
