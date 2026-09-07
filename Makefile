.PHONY: help install run run-mock run-all test typecheck check \
        mock-webhook mock-poll mock-csv mock-reset mock-all clean

APP_DIR := app
SPECS   := specs

help:
	@echo "Order Management System"
	@echo ""
	@echo "Setup"
	@echo "  make install       Install backend dependencies (uv sync)"
	@echo ""
	@echo "Running"
	@echo "  make run           Run the main app on :8000"
	@echo "  make run-mock      Run the mock polling upstream on :8001"
	@echo "  make run-all       Run both together; Ctrl+C stops both"
	@echo ""
	@echo "Testing"
	@echo "  make test          Run the test suite"
	@echo "  make typecheck     Run mypy --strict"
	@echo "  make check         test + typecheck"
	@echo ""
	@echo "Mock orders (run against an already-running 'make run' / 'make run-all')"
	@echo "  make mock-webhook  Replay specs/webhook_orders.jsonl against the webhook endpoint"
	@echo "                     (pass extra flags with ARGS, e.g. make mock-webhook ARGS=\"--delay 0.05\")"
	@echo "  make mock-poll     Force an immediate poll cycle"
	@echo "  make mock-csv      Upload specs/orders_4.csv"
	@echo "  make mock-reset    Rewind the mock upstream's poll cursor to the start of its file"
	@echo "  make mock-all      Run mock-webhook, mock-poll, and mock-csv together"
	@echo ""
	@echo "  make clean         Remove the local SQLite db and test/type-check caches"

install:
	@command -v uv >/dev/null 2>&1 || { \
		echo "uv not found — install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; \
	}
	cd $(APP_DIR) && uv sync

run:
	cd $(APP_DIR) && uv run uvicorn app.main:app --reload

run-mock:
	cd $(APP_DIR) && uv run uvicorn mock_upstream.app:app --port 8001

run-all:
	cd $(APP_DIR); \
	uv run uvicorn mock_upstream.app:app --port 8001 & \
	mock_pid=$$!; \
	trap "kill $$mock_pid 2>/dev/null" EXIT INT TERM; \
	uv run uvicorn app.main:app --reload

test:
	cd $(APP_DIR) && uv run pytest

typecheck:
	cd $(APP_DIR) && uv run mypy --strict app tests

check: test typecheck

mock-webhook:
	cd $(APP_DIR) && uv run python scripts/replay_webhook.py $(ARGS)

mock-poll:
	curl -sf -X POST http://localhost:8000/ingest/poll/trigger | python3 -m json.tool

mock-csv:
	curl -sf -F "file=@$(SPECS)/orders_4.csv" http://localhost:8000/ingest/csv | python3 -m json.tool

mock-reset:
	curl -sf -X POST http://localhost:8001/reset
	@echo

mock-all: mock-webhook mock-poll mock-csv

clean:
	rm -f $(APP_DIR)/order_management.db $(APP_DIR)/order_management.db-shm $(APP_DIR)/order_management.db-wal
	rm -rf $(APP_DIR)/.pytest_cache $(APP_DIR)/.mypy_cache
