from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KNOWN_ITEMS_PATH = Path(__file__).resolve().parent.parent / "data" / "known_menu_items.json"


@dataclass(frozen=True)
class ParsedCsvItem:
    name: str
    matched: bool


@lru_cache
def load_known_items(path: Path = KNOWN_ITEMS_PATH) -> frozenset[str]:
    return frozenset(json.loads(path.read_text()))


def _split_on_unparenthesized_commas(line: str) -> list[str]:
    tokens: list[str] = []
    depth = 0
    current: list[str] = []
    for char in line:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "," and depth == 0:
            tokens.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    tokens.append("".join(current).strip())
    return [token for token in tokens if token]


def _merge_tokens(tokens: list[str], known_items: frozenset[str]) -> list[ParsedCsvItem]:
    results: list[ParsedCsvItem] = []
    i = 0
    n = len(tokens)
    while i < n:
        for j in range(n - 1, i - 1, -1):
            candidate = ", ".join(tokens[i : j + 1])
            if candidate in known_items:
                results.append(ParsedCsvItem(name=candidate, matched=True))
                i = j + 1
                break
        else:
            results.append(ParsedCsvItem(name=tokens[i], matched=False))
            i += 1
    return results


def parse_items_field(raw: str, known_items: frozenset[str] | None = None) -> list[ParsedCsvItem]:
    """Parse a CSV `items` field into individual menu items, per plan §4.3.

    1. Split on newlines (used when an item's own name contains a comma inside
       parentheses) into candidate lines.
    2. Split each line on commas that are not inside parentheses into candidate tokens.
    3. Greedily re-merge adjacent tokens against the known-menu-item catalog, longest
       match first, so a menu item with unparenthesized commas in its own name (e.g.
       "Two eggs any style with bacon or sausage, hash browns, and toast") is recovered
       as one item instead of being shredded. A token (or merged span) with no catalog
       match is still emitted, flagged unmatched, and its raw text preserved.
    """
    if known_items is None:
        known_items = load_known_items()

    if not raw or not raw.strip():
        return []

    results: list[ParsedCsvItem] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        tokens = _split_on_unparenthesized_commas(line)
        results.extend(_merge_tokens(tokens, known_items))
    return results
