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
from evaluate.result_match import calculate_ex_bird  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate [{id, sql}] predictions against input JSON gold SQL.",
    )
    parser.add_argument("--input", required=True, help="Gold input JSON/JSONL with sql or SQL field.")
    parser.add_argument("--predictions", required=True, help="Prediction JSON/JSONL with id and SQL.")
    parser.add_argument("--details-output", default="", help="Optional JSON path for per-sample details.")
    parser.add_argument("--db-config", required=True, help="Database YAML/JSON config path.")
    parser.add_argument(
        "--metric",
        choices=("ex", "ves", "all"),
        default="all",
        help="Metric to evaluate. Defaults to all (EX and VES).",
    )
    parser.add_argument(
        "--ves-repeats",
        type=int,
        default=10,
        help="Paired predicted/gold timing runs for VES. Defaults to 10.",
    )
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
            metric=args.metric,
        )
        details.append(detail)
        metric_values = []
        if args.metric in {"ex", "all"}:
            metric_values.append(f"ex_bird={detail['ex_bird']}")
        if args.metric in {"ves", "all"}:
            metric_values.append(f"ves={detail['ves']:.2f}")
        print(
            "[eval] "
            f"{len(details)}/{len(gold_rows)} "
            f"id={current_id} difficulty={detail['difficulty']} "
            f"{' '.join(metric_values)} "
            f"status={detail['status']}",
            file=sys.stderr,
        )

    if args.details_output:
        write_records(args.details_output, details)

    _print_metrics(details, args.metric)


def _evaluate_one(
    *,
    row: Mapping[str, Any],
    pred_row: Mapping[str, Any] | None,
    row_index: int,
    config: PostgresConfig,
    repeats: int,
    metric: str,
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
        "ex_bird": 0,
        "ves": 0.0,
        "ves_time_ratio": 0.0,
        "ves_raw_ratios": [],
        "ves_filtered_ratios": [],
        "gold_time_sec": None,
        "pred_time_sec": None,
        "gold_time_secs": [],
        "pred_time_secs": [],
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

    pred_result = execute_sql(generated_sql, config)
    if pred_result.status != "ok":
        base_detail.update(
            status="pred_execution_error",
            error_type=pred_result.status,
            error_message=pred_result.error,
        )
        return base_detail

    gold_result = execute_sql(target_sql, config)
    if gold_result.status != "ok":
        base_detail.update(
            status="gold_execution_error",
            error_type=gold_result.status,
            error_message=gold_result.error,
        )
        return base_detail

    ex_bird = calculate_ex_bird(pred_result.rows, gold_result.rows)
    base_detail.update(
        ex_bird=ex_bird,
        status="correct" if ex_bird else "result_mismatch",
        pred_result_count=len(pred_result.rows),
        gold_result_count=len(gold_result.rows),
    )

    if metric not in {"ves", "all"} or not ex_bird:
        return base_detail

    pred_times, gold_times, timing_error = _execute_ves_repeated(
        generated_sql,
        target_sql,
        config,
        repeats,
    )
    if timing_error is not None:
        side, error = timing_error
        base_detail.update(
            status=f"{side}_timing_error",
            error_type=error.status,
            error_message=error.error,
            pred_time_sec=_mean_or_none(pred_times),
            gold_time_sec=_mean_or_none(gold_times),
            pred_time_secs=pred_times,
            gold_time_secs=gold_times,
        )
        return base_detail

    ves, time_ratio, raw_ratios, filtered_ratios = compute_ves_score(
        pred_times,
        gold_times,
    )
    base_detail.update(
        ves=ves,
        ves_time_ratio=time_ratio,
        ves_raw_ratios=raw_ratios,
        ves_filtered_ratios=filtered_ratios,
        pred_time_sec=_mean_or_none(pred_times),
        gold_time_sec=_mean_or_none(gold_times),
        pred_time_secs=pred_times,
        gold_time_secs=gold_times,
    )
    return base_detail


def _execute_ves_repeated(
    pred_sql: str,
    target_sql: str,
    config: PostgresConfig,
    repeats: int,
) -> tuple[list[float], list[float], tuple[str, ExecutionResult] | None]:
    pred_times: list[float] = []
    gold_times: list[float] = []
    for _ in range(repeats):
        pred_result = execute_sql(pred_sql, config, fetch_rows=False)
        if pred_result.status != "ok":
            return pred_times, gold_times, ("pred", pred_result)
        pred_times.append(pred_result.elapsed_sec)

        gold_result = execute_sql(target_sql, config, fetch_rows=False)
        if gold_result.status != "ok":
            return pred_times, gold_times, ("gold", gold_result)
        gold_times.append(gold_result.elapsed_sec)
    return pred_times, gold_times, None


def clean_abnormal(values: list[float]) -> list[float]:
    """Apply BIRD's strict mean ± 3 population-standard-deviation filter."""

    if not values:
        return []
    mean = statistics.fmean(values)
    std = statistics.pstdev(values)
    lower = mean - 3 * std
    upper = mean + 3 * std
    return [value for value in values if lower < value < upper]


def compute_ves_score(
    pred_times: list[float],
    gold_times: list[float],
) -> tuple[float, float, list[float], list[float]]:
    """Compute BIRD VES from paired timing ratios."""

    if len(pred_times) != len(gold_times):
        raise ValueError("Predicted and gold timing lists must have equal length.")
    if not pred_times or any(value <= 0 for value in pred_times):
        return 0.0, 0.0, [], []

    raw_ratios = [gold / predicted for predicted, gold in zip(pred_times, gold_times)]
    filtered_ratios = clean_abnormal(raw_ratios)
    if not filtered_ratios:
        return 0.0, 0.0, raw_ratios, []

    time_ratio = statistics.fmean(filtered_ratios)
    ves = math.sqrt(time_ratio) * 100.0
    return ves, time_ratio, raw_ratios, filtered_ratios


def _mean_or_none(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


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
        search_path=_default_search_path(row),
    )


def _default_search_path(row: Mapping[str, Any]) -> str:
    schema = db_id(row)
    return f"{schema},public" if schema else "public"


def _print_metrics(details: list[dict[str, Any]], metric: str) -> None:
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
    if metric == "ex":
        print(f"{'difficulty':<14} {'count':>7} {'EX':>10}")
    elif metric == "ves":
        print(f"{'difficulty':<14} {'count':>7} {'VES':>10}")
    else:
        print(f"{'difficulty':<14} {'count':>7} {'EX':>10} {'VES':>10}")
    for key in ordered_keys:
        _print_metric_row(key, groups[key], metric)
    _print_metric_row("all", details, metric)


def _print_metric_row(name: str, rows: list[dict[str, Any]], metric: str) -> None:
    count = len(rows)
    ex_bird = (
        sum(int(item.get("ex_bird") or 0) for item in rows) / count * 100.0
        if count
        else 0.0
    )
    ves = sum(float(item.get("ves") or 0.0) for item in rows) / count if count else 0.0
    if metric == "ex":
        print(f"{name:<14} {count:>7} {ex_bird:>9.2f}%")
    elif metric == "ves":
        print(f"{name:<14} {count:>7} {ves:>9.2f}")
    else:
        print(f"{name:<14} {count:>7} {ex_bird:>9.2f}% {ves:>9.2f}")


if __name__ == "__main__":
    main()
