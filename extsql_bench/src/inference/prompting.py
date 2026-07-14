"""Prompt-template rendering for text-to-SQL inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from common.data import (
    db_id,
    question_text,
    redact_gold_fields,
    schema_text,
)


class SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def load_template(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def render_prompt(
    row: Mapping[str, Any],
    *,
    template: str,
    schema_dir: str | Path | None = None,
    schema_loader: Callable[[str], str] | None = None,
    dialect: str = "PostgreSQL",
) -> str:
    current_db_id = db_id(row)
    schema = schema_text(row) or load_schema_for_db(schema_dir, current_db_id)
    if not schema and schema_loader and current_db_id:
        schema = schema_loader(current_db_id)
    oracle_function_and_operator = _oracle_function_and_operator_text(row)
    variables = SafeFormatDict(
        {
            "dialect": dialect,
            "id": str(row.get("id") or ""),
            "db_id": current_db_id,
            "question": question_text(row),
            "schema": schema,
            "db_schema": schema,
            "schema_section": _section("Database schema", schema),
            "oracle": oracle_function_and_operator,
            "oracle_function_and_operator": oracle_function_and_operator,
            # Keep legacy placeholders empty so an old template cannot leak
            # benchmark evidence into inference.
            "evidence": "",
            "evidence_section": "",
            "extra": json.dumps(_redact_inference_fields(row), ensure_ascii=False, indent=2),
        }
    )
    for key, value in row.items():
        variables.setdefault(str(key), _stringify(value))
    return template.format_map(variables)


def load_schema_for_db(schema_dir: str | Path | None, database_id: str) -> str:
    if not schema_dir or not database_id:
        return ""
    root = Path(schema_dir)
    candidates = [
        root / f"{database_id}.txt",
        root / f"{database_id}_schema.txt",
        root / f"{database_id}.schema.txt",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()

    matches = sorted(root.glob(f"*{database_id}*schema*.txt"))
    if matches:
        return matches[0].read_text(encoding="utf-8").strip()
    return ""


def _section(title: str, content: str) -> str:
    text = str(content or "").strip()
    if not text:
        return f"{title}:\n<not provided>"
    return f"{title}:\n{text}"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _redact_inference_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    redacted = redact_gold_fields(row)
    for key in ("evidence", "hint", "knowledge", "external_knowledge"):
        redacted.pop(key, None)
    return redacted


def _oracle_function_and_operator_text(row: Mapping[str, Any]) -> str:
    sql_objects = row.get("sql_objects")
    if not isinstance(sql_objects, list):
        return "<not provided>"

    grouped: dict[str, list[str]] = {"function": [], "operator": []}
    for item in sql_objects:
        if not isinstance(item, Mapping):
            continue
        object_type = str(item.get("type") or "").strip().lower()
        value = str(item.get("value") or "").strip()
        if object_type not in grouped or not value or value in grouped[object_type]:
            continue
        grouped[object_type].append(value)

    lines: list[str] = []
    if grouped["function"]:
        lines.append("Functions: " + ", ".join(grouped["function"]))
    if grouped["operator"]:
        lines.append("Operators: " + ", ".join(grouped["operator"]))
    return "\n".join(lines) or "<not provided>"
