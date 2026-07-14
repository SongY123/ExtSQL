#!/usr/bin/env python3
"""Evaluate SQL predictions on PostgreSQL with EX and VES."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "extsql_bench" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from common.config import DatabaseSettings, load_database_settings  # noqa: E402
from common.data import (  # noqa: E402
    db_id,
    difficulty,
    gold_sql,
    load_records,
    prediction_sql,
    sample_id,
    write_records,
)
from evaluate.postgres import ExecutionResult, PostgresConfig, execute_sql  # noqa: E402
from evaluate.result_match import calculate_ex  # noqa: E402


EPS = 1e-9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate [{id, sql}] predictions against input JSON gold SQL.",
    )
    parser.add_argument("--input", required=True, help="Gold input JSON/JSONL with sql or SQL field.")
    parser.add_argument("--predictions", required=True, help="Prediction JSON/JSONL with id and SQL.")
    parser.add_argument("--details-output", default="", help="Optional JSON path for per-sample details.")
    parser.add_argument("--db-config", required=True, help="Database YAML/JSON config path.")
    parser.add_argument("--ves-repeats", type=int, default=1, help="Median timing repeats per SQL.")
    parser.add_argument("--skip-missing", action="store_true", help="Skip samples without a prediction.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_settings = load_database_settings(args.db_config)
    gold_rows = load_records(args.input)
    prediction_rows = load_records(args.predictions)
    prediction_by_id = {
        sample_id(row, index): row for index, row in enumerate(prediction_rows, start=1)
    }

    details: list[dict[str, Any]] = []
    for index, row in enumerate(gold_rows, start=1):
        current_id = sample_id(row, index)
        pred_row = prediction_by_id.get(current_id)
        if pred_row is None and args.skip_missing:
            continue

        config = _resolve_db_config(database_settings, row)
        detail = _evaluate_one(
            row=row,
            pred_row=pred_row,
            row_index=index,
            config=config,
            repeats=max(1, args.ves_repeats),
        )
        details.append(detail)
        print(
            "[eval] "
            f"{len(details)}/{len(gold_rows)} "
            f"id={current_id} difficulty={detail['difficulty']} "
            f"ex={detail['ex']} ves={detail['ves']:.2f} "
            f"status={detail['status']}",
            file=sys.stderr,
        )

    if args.details_output:
        write_records(args.details_output, details)

    _print_metrics(details)


def _evaluate_one(
    *,
    row: Mapping[str, Any],
    pred_row: Mapping[str, Any] | None,
    row_index: int,
    config: PostgresConfig,
    repeats: int,
) -> dict[str, Any]:
    current_id = sample_id(row, row_index)
    target_sql = gold_sql(row)
    generated_sql = prediction_sql(pred_row or {})
    base_detail: dict[str, Any] = {
        "id": current_id,
        "db_id": db_id(row),
        "difficulty": difficulty(row),
        "gold_sql": target_sql,
        "pred_sql": generated_sql,
        "ex": 0,
        "ex_bird": 0,
        "ves": 0.0,
        "gold_time_sec": None,
        "pred_time_sec": None,
        "status": "wrong",
        "error_type": "",
        "error_message": "",
    }

    if pred_row is None:
        base_detail.update(
            status="missing_prediction",
            error_type="missing_prediction",
            error_message="No prediction found for id.",
        )
        return base_detail

    if not target_sql:
        base_detail.update(
            status="gold_empty_sql",
            error_type="gold_empty_sql",
            error_message="Gold SQL is empty.",
        )
        return base_detail

    pred_execs, gold_execs = _execute_repeated(generated_sql, target_sql, config, repeats)
    pred_first = pred_execs[0] if pred_execs else None
    gold_first = gold_execs[0] if gold_execs else None

    if pred_first is None or pred_first.status != "ok":
        error = pred_first or ExecutionResult("execution_error", [], 0.0, "Prediction did not execute.")
        base_detail.update(
            status="pred_execution_error",
            error_type=error.status,
            error_message=error.error,
            pred_time_sec=error.elapsed_sec,
        )
        return base_detail

    if gold_first is None or gold_first.status != "ok":
        error = gold_first or ExecutionResult("execution_error", [], 0.0, "Gold SQL did not execute.")
        base_detail.update(
            status="gold_execution_error",
            error_type=error.status,
            error_message=error.error,
            pred_time_sec=_median_time(pred_execs),
            gold_time_sec=error.elapsed_sec,
        )
        return base_detail

    ex_eq, ex_bird = calculate_ex(pred_first.rows, gold_first.rows)
    pred_time = _median_time(pred_execs)
    gold_time = _median_time(gold_execs)
    ves = math.sqrt(max(gold_time, EPS) / max(pred_time, EPS)) * 100.0 if ex_eq else 0.0
    base_detail.update(
        ex=ex_eq,
        ex_bird=ex_bird,
        ves=ves,
        gold_time_sec=gold_time,
        pred_time_sec=pred_time,
        status="correct" if ex_eq else "result_mismatch",
        pred_result_count=len(pred_first.rows),
        gold_result_count=len(gold_first.rows),
    )
    return base_detail


def _execute_repeated(
    pred_sql: str,
    target_sql: str,
    config: PostgresConfig,
    repeats: int,
) -> tuple[list[ExecutionResult], list[ExecutionResult]]:
    pred_execs: list[ExecutionResult] = []
    gold_execs: list[ExecutionResult] = []
    for _ in range(repeats):
        pred_result = execute_sql(pred_sql, config)
        pred_execs.append(pred_result)
        if pred_result.status != "ok":
            break
        gold_result = execute_sql(target_sql, config)
        gold_execs.append(gold_result)
        if gold_result.status != "ok":
            break
    return pred_execs, gold_execs


def _median_time(results: list[ExecutionResult]) -> float:
    ok_times = [item.elapsed_sec for item in results if item.status == "ok"]
    if not ok_times:
        return 0.0
    return float(statistics.median(ok_times))


def _resolve_db_config(
    settings: DatabaseSettings,
    row: Mapping[str, Any],
) -> PostgresConfig:
    return PostgresConfig(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
        connect_timeout=settings.connect_timeout,
        statement_timeout_ms=int(settings.statement_timeout * 1000),
        search_path=settings.search_path or _default_search_path(row),
    )


def _default_search_path(row: Mapping[str, Any]) -> str:
    schema = db_id(row)
    return f"{schema},public" if schema else "public"


def _print_metrics(details: list[dict[str, Any]]) -> None:
    if not details:
        print("No evaluated samples.")
        return

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in details:
        groups.setdefault(str(item.get("difficulty") or "unknown"), []).append(item)

    order = ["easy", "medium", "hard", "extra_hard", "unknown"]
    ordered_keys = [key for key in order if key in groups]
    ordered_keys.extend(sorted(key for key in groups if key not in set(ordered_keys)))

    print("\nEvaluation metrics")
    print(f"{'difficulty':<14} {'count':>7} {'EX':>10} {'VES':>10}")
    for key in ordered_keys:
        _print_metric_row(key, groups[key])
    _print_metric_row("all", details)


def _print_metric_row(name: str, rows: list[dict[str, Any]]) -> None:
    count = len(rows)
    ex = sum(int(item.get("ex") or 0) for item in rows) / count * 100.0 if count else 0.0
    ves = sum(float(item.get("ves") or 0.0) for item in rows) / count if count else 0.0
    print(f"{name:<14} {count:>7} {ex:>9.2f}% {ves:>9.2f}")


if __name__ == "__main__":
    main()
