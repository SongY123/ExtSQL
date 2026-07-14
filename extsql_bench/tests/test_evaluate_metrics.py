from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from common.config import DatabaseSettings
from evaluate.evaluate import (
    _evaluate_one,
    _resolve_db_config,
    clean_abnormal,
    compute_ves_score,
)
from evaluate.postgres import ExecutionResult, PostgresConfig, _set_search_path_sql
from evaluate.result_match import calculate_ex_bird


class BirdExecutionAccuracyTests(unittest.TestCase):
    def test_ignores_row_order_and_duplicate_rows(self) -> None:
        predicted = [(2,), (1,), (1,)]
        gold = [(1,), (2,)]

        self.assertEqual(calculate_ex_bird(predicted, gold), 1)

    def test_preserves_column_order(self) -> None:
        predicted = [(1, 2)]
        gold = [(2, 1)]

        self.assertEqual(calculate_ex_bird(predicted, gold), 0)


class EvaluationSearchPathTests(unittest.TestCase):
    def test_current_schema_precedes_public_even_with_config_override(self) -> None:
        settings = DatabaseSettings(
            connection_type="postgresql",
            host="localhost",
            port=5432,
            database="postgis_db",
            user="postgres",
            password="postgres",
            connect_timeout=10,
            statement_timeout=60,
            search_path="public",
        )

        config = _resolve_db_config(
            settings,
            {"database": {"db_id": "nyc_workshop"}},
        )

        self.assertEqual(config.search_path, "nyc_workshop,public")
        self.assertEqual(
            _set_search_path_sql(config.search_path),
            'SET search_path TO "nyc_workshop", "public"',
        )


class BirdVesTests(unittest.TestCase):
    def test_filters_ratio_outliers_with_three_sigma_rule(self) -> None:
        ratios = [1.0] * 10 + [100.0]

        self.assertEqual(clean_abnormal(ratios), [1.0] * 10)

    def test_averages_per_run_ratios_before_square_root(self) -> None:
        predicted_times = [1.0, 100.0]
        gold_times = [2.0, 100.0]

        score, time_ratio, raw_ratios, filtered_ratios = compute_ves_score(
            predicted_times,
            gold_times,
        )

        self.assertEqual(raw_ratios, [2.0, 1.0])
        self.assertEqual(filtered_ratios, raw_ratios)
        self.assertAlmostEqual(time_ratio, 1.5)
        self.assertAlmostEqual(score, math.sqrt(1.5) * 100.0)

    def test_matches_official_empty_filtered_list_behavior(self) -> None:
        score, time_ratio, _, filtered_ratios = compute_ves_score(
            [1.0, 1.0, 1.0],
            [1.0, 1.0, 1.0],
        )

        self.assertEqual(filtered_ratios, [])
        self.assertEqual(time_ratio, 0.0)
        self.assertEqual(score, 0.0)


class EvaluationModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = PostgresConfig(
            host="localhost",
            port=5432,
            user="postgres",
            password="postgres",
            database="test",
        )
        self.row = {"id": "1", "sql": "SELECT gold", "difficulty": "easy"}
        self.prediction = {"id": "1", "sql": "SELECT predicted"}

    @patch("evaluate.evaluate.execute_sql")
    def test_ex_mode_skips_repeated_timing(self, execute_sql_mock) -> None:
        execute_sql_mock.side_effect = [
            ExecutionResult("ok", [(1,)], 0.1),
            ExecutionResult("ok", [(1,)], 0.2),
        ]

        detail = _evaluate_one(
            row=self.row,
            pred_row=self.prediction,
            row_index=1,
            config=self.config,
            repeats=100,
            metric="ex",
        )

        self.assertNotIn("ex", detail)
        self.assertEqual(detail["ex_bird"], 1)
        self.assertEqual(detail["ves"], 0.0)
        self.assertEqual(execute_sql_mock.call_count, 2)

    @patch("evaluate.evaluate.execute_sql")
    def test_all_mode_uses_paired_predicted_then_gold_timings(self, execute_sql_mock) -> None:
        execute_sql_mock.side_effect = [
            ExecutionResult("ok", [(1,)], 0.1),
            ExecutionResult("ok", [(1,)], 0.2),
            ExecutionResult("ok", [], 1.0),
            ExecutionResult("ok", [], 2.0),
            ExecutionResult("ok", [], 4.0),
            ExecutionResult("ok", [], 4.0),
        ]

        detail = _evaluate_one(
            row=self.row,
            pred_row=self.prediction,
            row_index=1,
            config=self.config,
            repeats=2,
            metric="all",
        )

        self.assertEqual(detail["ves_raw_ratios"], [2.0, 1.0])
        self.assertAlmostEqual(detail["ves"], math.sqrt(1.5) * 100.0)
        self.assertEqual(detail["pred_time_secs"], [1.0, 4.0])
        self.assertEqual(detail["gold_time_secs"], [2.0, 4.0])
        self.assertEqual(detail["pred_time_sec"], 2.5)
        self.assertEqual(detail["gold_time_sec"], 3.0)
        timed_calls = execute_sql_mock.call_args_list[2:]
        self.assertEqual(
            [call.args[0] for call in timed_calls],
            ["SELECT predicted", "SELECT gold", "SELECT predicted", "SELECT gold"],
        )
        self.assertTrue(all(call.kwargs == {"fetch_rows": False} for call in timed_calls))

    @patch("evaluate.evaluate.execute_sql")
    def test_result_mismatch_scores_zero_without_timing(self, execute_sql_mock) -> None:
        execute_sql_mock.side_effect = [
            ExecutionResult("ok", [(1,)], 0.1),
            ExecutionResult("ok", [(2,)], 0.2),
        ]

        detail = _evaluate_one(
            row=self.row,
            pred_row=self.prediction,
            row_index=1,
            config=self.config,
            repeats=100,
            metric="all",
        )

        self.assertNotIn("ex", detail)
        self.assertEqual(detail["ex_bird"], 0)
        self.assertEqual(detail["ves"], 0.0)
        self.assertEqual(detail["pred_time_secs"], [])
        self.assertEqual(detail["gold_time_secs"], [])
        self.assertEqual(execute_sql_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
