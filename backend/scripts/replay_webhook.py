"""Replay specs/webhook_orders.jsonl against a running webhook endpoint.

This is both a mock data injector (plan §8 — "an easy way to inject
additional orders") and the mechanism for exercising the webhook pipeline's
actual HTTP behavior — idempotent upsert on redelivery, cancellation
handling — which pytest against the ingestion function alone doesn't cover,
since that never goes over the wire.

Usage:
    uv run python scripts/replay_webhook.py
    uv run python scripts/replay_webhook.py --delay 0.05 --limit 50
    uv run python scripts/replay_webhook.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BACKEND_DIR.parent / "specs" / "webhook_orders.jsonl"


def replay(file_path: Path, base_url: str, delay_seconds: float, limit: int | None) -> None:
    lines = [line for line in file_path.read_text().splitlines() if line.strip()]
    if limit is not None:
        lines = lines[:limit]

    ok_count = 0
    failed_count = 0

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        for i, line in enumerate(lines, start=1):
            payload = json.loads(line)
            response = client.post("/ingest/webhook/orders", json=payload)
            if response.is_success:
                ok_count += 1
                marker = "OK"
            else:
                failed_count += 1
                marker = f"FAILED ({response.status_code}): {response.text}"
            print(f"[{i}/{len(lines)}] order_id={payload.get('order_id')} -> {marker}")

            if delay_seconds > 0 and i < len(lines):
                time.sleep(delay_seconds)

    print(f"\nDone: {ok_count} ok, {failed_count} failed, {len(lines)} total.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--file", type=Path, default=DEFAULT_FILE, help="Path to a webhook_orders.jsonl-shaped file"
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the running app")
    parser.add_argument(
        "--delay", type=float, default=0.0, help="Seconds to sleep between requests, to simulate bursty traffic"
    )
    parser.add_argument("--limit", type=int, default=None, help="Only replay the first N lines")
    args = parser.parse_args()

    replay(args.file, args.base_url, args.delay, args.limit)


if __name__ == "__main__":
    main()
