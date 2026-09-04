from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: object, connection_record: object) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_db() -> None:
    import app.models  # noqa: F401  # register all table models on SQLModel.metadata

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
