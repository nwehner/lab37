from __future__ import annotations

import atexit
import os
import tempfile
from collections.abc import Generator
from pathlib import Path

# Must run before any `app.*` module is imported (including by other test modules),
# since app.db builds its engine from settings read at import time. conftest.py is
# collected by pytest before test modules in this directory, so this runs first.
_tmp_dir = tempfile.TemporaryDirectory(prefix="order_mgmt_test_")
atexit.register(_tmp_dir.cleanup)
os.environ["ORDER_MGMT_DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir.name) / 'test.db'}"

import pytest  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_database() -> Generator[None, None, None]:
    init_db()
    yield
    SQLModel.metadata.drop_all(engine)
