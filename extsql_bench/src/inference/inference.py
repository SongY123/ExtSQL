#!/usr/bin/env python3
"""OpenAI-compatible text-to-SQL inference CLI entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "extsql_bench" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from common.config import load_database_settings, load_llm_settings  # noqa: E402
from common.data import load_records, prediction_sql, sample_id, write_records  # noqa: E402
from inference.llm import ChatConfig, OpenAICompatibleChatClient, clean_sql_response  # noqa: E402
from inference.postgres_schema import (  # noqa: E402
    PostgresSchemaConfig,
    PostgresSchemaLoader,
)
from inference.prompting import load_template, render_prompt  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate SQL predictions for ExtSQL-format JSON input.",
    )
    parser.add_argument("--input", required=True, help="Input JSON/JSONL file.")
    parser.add_argument("--output", required=True, help="Output JSON file: [{id, sql}].")
    parser.add_argument("--llm-config", required=True, help="LLM YAML/JSON config path.")
    parser.add_argument("--db-config", required=True, help="Database YAML/JSON config path.")
    parser.add_argument(
        "--prompt-template",
        default=str(PROJECT_ROOT / "prompts" / "postgres.txt"),
        help="TXT prompt template path.",
    )
    parser.add_argument("--schema-dir", default="", help="Optional directory containing DB schema txt files.")
    parser.add_argument("--dialect", default="PostgreSQL")
    parser.add_argument("--limit", type=int, default=0, help="0 means all rows.")
    parser.add_argument("--resume", action="store_true", help="Reuse existing predictions by id.")
    parser.add_argument("--save-every", type=int, default=1, help="Rewrite output every N new rows.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    llm_settings = load_llm_settings(args.llm_config)
    database_settings = load_database_settings(args.db_config)

    rows = load_records(args.input)
    if args.limit > 0:
        rows = rows[: args.limit]

    output_path = Path(args.output)
    existing = _load_existing(output_path) if args.resume else {}
    predictions_by_id: dict[str, dict[str, str]] = dict(existing)
    template = load_template(args.prompt_template)
    schema_loader = PostgresSchemaLoader(
        PostgresSchemaConfig(
            host=database_settings.host,
            port=database_settings.port,
            user=database_settings.user,
            password=database_settings.password,
            database=database_settings.database,
            connect_timeout=database_settings.connect_timeout,
        )
    )
    client = OpenAICompatibleChatClient(
        ChatConfig(
            model=llm_settings.model,
            api_key=llm_settings.api_key,
            base_url=llm_settings.base_url,
            temperature=llm_settings.temperature,
            max_tokens=llm_settings.max_tokens,
            request_timeout=llm_settings.timeout,
            retries=llm_settings.retries,
            retry_sleep=llm_settings.retry_sleep,
        )
    )

    completed = 0
    for index, row in enumerate(rows, start=1):
        current_id = sample_id(row, index)
        if current_id in predictions_by_id and predictions_by_id[current_id].get("sql"):
            continue

        prompt = render_prompt(
            row,
            template=template,
            schema_dir=args.schema_dir or None,
            schema_loader=schema_loader.load,
            dialect=args.dialect,
        )
        try:
            response = client.complete(
                prompt=prompt,
                system_prompt=llm_settings.system_prompt,
            )
            sql = clean_sql_response(response)
        except Exception as exc:  # noqa: BLE001 - keep batch running
            print(f"[error] id={current_id}: {exc}", file=sys.stderr)
            sql = ""

        predictions_by_id[current_id] = {"id": current_id, "sql": sql}
        completed += 1
        if completed % max(1, args.save_every) == 0:
            _write_in_input_order(output_path, rows, predictions_by_id)
        print(f"[infer] {len(predictions_by_id)}/{len(rows)} id={current_id}", file=sys.stderr)

    _write_in_input_order(output_path, rows, predictions_by_id)
    print(f"[done] wrote {output_path}")


def _load_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    existing: dict[str, dict[str, str]] = {}
    for index, row in enumerate(load_records(path), start=1):
        current_id = sample_id(row, index)
        existing[current_id] = {"id": current_id, "sql": prediction_sql(row)}
    return existing


def _write_in_input_order(
    path: Path,
    input_rows: list[dict],
    predictions_by_id: dict[str, dict[str, str]],
) -> None:
    ordered: list[dict[str, str]] = []
    for index, row in enumerate(input_rows, start=1):
        current_id = sample_id(row, index)
        if current_id in predictions_by_id:
            ordered.append(predictions_by_id[current_id])
    write_records(path, ordered)


if __name__ == "__main__":
    main()
