from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from inference.inference import _print_inference_metrics
from inference.llm import ChatConfig, OpenAICompatibleChatClient, _extract_usage


class UsageExtractionTests(unittest.TestCase):
    def test_extracts_chat_completion_usage(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=120,
                completion_tokens=30,
                total_tokens=999,
            )
        )

        self.assertEqual(_extract_usage(response), (120, 30, 150))

    def test_supports_input_output_token_names(self) -> None:
        response = {
            "usage": {
                "input_tokens": 80,
                "output_tokens": 20,
            }
        }

        self.assertEqual(_extract_usage(response), (80, 20, 100))

    def test_missing_usage_is_not_estimated(self) -> None:
        self.assertEqual(_extract_usage({}), (None, None, None))


class ChatCompletionMetricsTests(unittest.TestCase):
    @patch.object(OpenAICompatibleChatClient, "_build_client")
    def test_complete_with_metrics_returns_content_usage_and_time(self, build_client) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 1;"))],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=4,
                total_tokens=14,
            ),
        )
        create = unittest.mock.Mock(return_value=response)
        build_client.return_value = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        client = OpenAICompatibleChatClient(
            ChatConfig(model="test", api_key="test")
        )

        result = client.complete_with_metrics(prompt="question", system_prompt="")

        self.assertEqual(result.content, "SELECT 1;")
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 4)
        self.assertEqual(result.total_tokens, 14)
        self.assertGreaterEqual(result.inference_time_ms, 0.0)


class InferenceSummaryTests(unittest.TestCase):
    def test_prints_averages_by_difficulty_and_all(self) -> None:
        rows = [
            {"id": "1", "difficulty": "easy"},
            {"id": "2", "difficulty": "easy"},
            {"id": "3", "difficulty": "hard"},
        ]
        predictions = {
            "1": {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "inference_time_ms": 10,
            },
            "2": {
                "input_tokens": 200,
                "output_tokens": 40,
                "total_tokens": 240,
                "inference_time_ms": 30,
            },
            "3": {
                "input_tokens": 300,
                "output_tokens": 60,
                "total_tokens": 360,
                "inference_time_ms": 50,
            },
        }
        output = io.StringIO()

        with redirect_stdout(output):
            _print_inference_metrics(rows, predictions)

        text = output.getvalue()
        self.assertIn("easy", text)
        self.assertIn("150.00", text)
        self.assertIn("hard", text)
        self.assertIn("all", text)
        self.assertIn("200.00", text)
        self.assertIn("30.00", text)


if __name__ == "__main__":
    unittest.main()
