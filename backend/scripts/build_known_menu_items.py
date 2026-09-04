"""One-time build script for app/data/known_menu_items.json.

Unions item names from specs/webhook_orders.jsonl (`items`) and
specs/api_responses.jsonl (`data[*].name`) into a sorted catalog, per plan §4.3.
Re-run and re-commit the output only if the spec files change.
"""

from __future__ import annotations

import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SPECS_DIR = BACKEND_DIR.parent / "specs"
OUTPUT_PATH = BACKEND_DIR / "app" / "data" / "known_menu_items.json"


def build_catalog() -> list[str]:
    items: set[str] = set()

    with (SPECS_DIR / "webhook_orders.jsonl").open() as f:
        for line in f:
            record = json.loads(line)
            items.update(record.get("items", []))

    with (SPECS_DIR / "api_responses.jsonl").open() as f:
        for line in f:
            record = json.loads(line)
            data = record.get("data") or {}
            for item in data.values():
                items.add(item["name"])

    return sorted(items)


def main() -> None:
    catalog = build_catalog()
    OUTPUT_PATH.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Wrote {len(catalog)} known menu items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
