"""BIRD execution-result comparison rules for SQL evaluation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
from typing import Any, Iterable


def calculate_ex_bird(predicted_rows: Iterable[Any], gold_rows: Iterable[Any]) -> int:
    """Return BIRD EX: equality of result-row sets.

    This intentionally ignores row order and duplicate rows while preserving
    column order, matching BIRD's ``set(predicted_res) == set(gold_res)`` rule.
    Values are normalized only to make PostgreSQL-specific values hashable.
    """

    predicted = normalize_rows(predicted_rows)
    gold = normalize_rows(gold_rows)
    return 1 if set(predicted) == set(gold) else 0


def normalize_rows(rows: Iterable[Any] | None) -> list[tuple[Any, ...]]:
    if rows is None:
        return []

    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        if isinstance(row, tuple):
            values = row
        elif isinstance(row, list):
            values = tuple(row)
        else:
            values = (row,)
        normalized.append(tuple(_normalize_value(value) for value in values))
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, memoryview):
        return value.tobytes().hex()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, tuple):
        return tuple(_normalize_value(item) for item in value)
    if isinstance(value, list):
        return tuple(_normalize_value(item) for item in value)
    if isinstance(value, dict):
        normalized = {
            str(key): _normalize_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    if hasattr(value, "item"):
        try:
            scalar = value.item()
        except Exception:
            scalar = None
        else:
            if scalar is not value:
                return _normalize_value(scalar)
    return value
