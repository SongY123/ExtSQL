"""Execution-result comparison rules for SQL evaluation.

The EX rule uses denotation matching: row order is ignored, and column order may
be permuted when the two result sets are otherwise equivalent. Values are
normalized first so PostgreSQL JSON, bytes, dates, and Decimals remain
comparable and hashable.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from itertools import product
import json
import random
from typing import Any, Iterable


def calculate_ex(predicted_rows: Iterable[Any], gold_rows: Iterable[Any]) -> tuple[int, int]:
    predicted = normalize_rows(predicted_rows)
    gold = normalize_rows(gold_rows)
    ex_eq = 1 if result_eq(gold, predicted, order_matters=False) else 0
    ex_bird = 1 if set(predicted) == set(gold) else 0
    return ex_eq, ex_bird


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


def result_eq(
    result1: list[tuple[Any, ...]],
    result2: list[tuple[Any, ...]],
    order_matters: bool,
) -> bool:
    if len(result1) == 0 and len(result2) == 0:
        return True
    if len(result1) != len(result2):
        return False
    if not result1 or not result2:
        return False

    num_cols = len(result1[0])
    if len(result2[0]) != num_cols:
        return False

    if not _quick_rej(result1, result2, order_matters):
        return False

    tab1_sets_by_columns = [{row[i] for row in result1} for i in range(num_cols)]
    for perm in _get_constraint_permutation(tab1_sets_by_columns, result2):
        if len(perm) != len(set(perm)):
            continue
        if num_cols == 1:
            result2_perm = result2
        else:
            result2_perm = [_permute_tuple(element, perm) for element in result2]
        if order_matters:
            if result1 == result2_perm:
                return True
        elif set(result1) == set(result2_perm) and _multiset_eq(result1, result2_perm):
            return True
    return False


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


def _permute_tuple(element: tuple[Any, ...], perm: tuple[int, ...]) -> tuple[Any, ...]:
    return tuple(element[i] for i in perm)


def _unorder_row(row: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(row, key=lambda value: str(value) + str(type(value))))


def _quick_rej(
    result1: list[tuple[Any, ...]],
    result2: list[tuple[Any, ...]],
    order_matters: bool,
) -> bool:
    left = [_unorder_row(row) for row in result1]
    right = [_unorder_row(row) for row in result2]
    if order_matters:
        return left == right
    return set(left) == set(right)


def _multiset_eq(left: list[Any], right: list[Any]) -> bool:
    if len(left) != len(right):
        return False
    counts: dict[Any, int] = defaultdict(int)
    for item in left:
        counts[item] += 1
    for item in right:
        counts[item] -= 1
        if counts[item] < 0:
            return False
    return True


def _get_constraint_permutation(
    tab1_sets_by_columns: list[set[Any]],
    result2: list[tuple[Any, ...]],
):
    num_cols = len(result2[0])
    perm_constraints = [set(range(num_cols)) for _ in range(num_cols)]
    if num_cols <= 3:
        return product(*perm_constraints)

    for _ in range(20):
        random_tab2_row = random.choice(result2)
        for tab1_col in range(num_cols):
            for tab2_col in set(perm_constraints[tab1_col]):
                if random_tab2_row[tab2_col] not in tab1_sets_by_columns[tab1_col]:
                    perm_constraints[tab1_col].remove(tab2_col)
    return product(*perm_constraints)
