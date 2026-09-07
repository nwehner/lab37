from __future__ import annotations

import csv
from pathlib import Path

from app.ingestion.csv_item_parser import load_known_items, parse_items_field

SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "specs"
CSV_FILENAMES = ["orders_1.csv", "orders_2.csv", "orders_3.csv", "orders_4.csv"]
AMBIGUOUS_ITEM = "Two eggs any style with bacon or sausage, hash browns, and toast"


def test_known_items_catalog_contains_the_ambiguous_item() -> None:
    known = load_known_items()
    assert AMBIGUOUS_ITEM in known


def test_parses_simple_comma_separated_line() -> None:
    parsed = parse_items_field("Fried banana, Sweet tea, Apple pie")
    assert [p.name for p in parsed] == ["Fried banana", "Sweet tea", "Apple pie"]
    assert all(p.matched for p in parsed)


def test_parses_newline_separated_field_with_parenthesized_commas() -> None:
    raw = (
        "Multigrain sandwich loaf\n"
        "Milkshakes (vanilla, chocolate, strawberry)\n"
        "Philly cheesesteak"
    )
    parsed = parse_items_field(raw)
    assert [p.name for p in parsed] == [
        "Multigrain sandwich loaf",
        "Milkshakes (vanilla, chocolate, strawberry)",
        "Philly cheesesteak",
    ]
    assert all(p.matched for p in parsed)


def test_recovers_ambiguous_item_with_unparenthesized_commas_instead_of_shredding_it() -> None:
    raw = f"Espresso, {AMBIGUOUS_ITEM}, Croissant"
    parsed = parse_items_field(raw)
    assert [p.name for p in parsed] == ["Espresso", AMBIGUOUS_ITEM, "Croissant"]
    assert all(p.matched for p in parsed)


def test_unmatched_token_is_preserved_and_flagged() -> None:
    known = frozenset({"Espresso", "Croissant"})
    parsed = parse_items_field("Espresso, Some Unlisted Item, Croissant", known_items=known)
    assert [p.name for p in parsed] == ["Espresso", "Some Unlisted Item", "Croissant"]
    assert [p.matched for p in parsed] == [True, False, True]


def test_empty_field_parses_to_no_items() -> None:
    assert parse_items_field("") == []
    assert parse_items_field("   ") == []


def _iter_unique_csv_rows() -> list[dict[str, str]]:
    with (SPECS_DIR / "orders_4.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def test_full_csv_corpus_parses_with_no_unmatched_items() -> None:
    """orders_4.csv is a cumulative superset of orders_1..3.csv, so parsing
    it alone against the real known-item catalog covers every row in the corpus."""
    known = load_known_items()
    rows = _iter_unique_csv_rows()
    assert len(rows) > 0

    unmatched: list[tuple[str, str]] = []
    for row in rows:
        for item in parse_items_field(row["items"], known):
            if not item.matched:
                unmatched.append((row["items"], item.name))

    assert unmatched == []


def test_orders_1_through_3_are_prefixes_covered_by_orders_4() -> None:
    with (SPECS_DIR / "orders_4.csv").open(newline="") as f:
        rows_4 = {tuple(row.values()) for row in csv.DictReader(f)}

    for filename in ["orders_1.csv", "orders_2.csv", "orders_3.csv"]:
        with (SPECS_DIR / filename).open(newline="") as f:
            rows = {tuple(row.values()) for row in csv.DictReader(f)}
        assert rows <= rows_4
