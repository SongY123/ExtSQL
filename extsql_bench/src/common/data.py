"""Input/output helpers for ExtSQL benchmark JSON files."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


JsonObject = dict[str, Any]

GOLD_SQL_KEYS = ("sql", "SQL", "gold_sql", "query", "output")
PRED_SQL_KEYS = ("sql", "SQL", "pred_sql", "predict_sql", "predicted_sql")


def load_records(path: str | Path) -> list[JsonObject]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        return _load_jsonl(source)

    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = _records_from_object(payload)
    else:
        raise ValueError(f"Expected JSON array/object in {source}")

    return _validate_records(rows, source)


def write_records(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(list(rows), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sample_id(row: Mapping[str, Any], index: int) -> str:
    value = first_present(row, ("id", "question_id", "idx", "sql_idx"))
    if value is None or str(value).strip() == "":
        return str(index)
    return str(value)


def question_text(row: Mapping[str, Any]) -> str:
    conversation = _conversation_text(row, role_index=0)
    if conversation:
        return conversation

    instruction = _as_text(row.get("instruction"))
    input_text = _as_text(row.get("input"))
    if instruction and input_text:
        return f"{instruction}\n\n{input_text}"
    if instruction:
        return instruction

    value = first_present(row, ("question", "input", "prompt", "nl", "utterance"))
    return _as_text(value)


def gold_sql(row: Mapping[str, Any]) -> str:
    value = first_present(row, GOLD_SQL_KEYS)
    if value is not None:
        return _as_text(value)
    return _conversation_text(row, role_index=1)


def prediction_sql(row: Mapping[str, Any]) -> str:
    value = first_present(row, PRED_SQL_KEYS)
    return _as_text(value)


def db_id(row: Mapping[str, Any]) -> str:
    value = first_present(row, ("db_id", "db_name", "database_id"))
    if value is not None:
        return _as_text(value)
    database = row.get("database")
    if isinstance(database, Mapping):
        value = first_present(database, ("db_id", "db_name", "database_id", "name"))
        if value is not None:
            return _as_text(value)
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        value = first_present(metadata, ("db_id", "db_name", "database_id"))
        if value is not None:
            return _as_text(value)
    match = re.search(r"\[DB_ID\]\s*([^\s\[]+)", question_text(row))
    if match:
        return match.group(1).strip()
    return ""


def difficulty(row: Mapping[str, Any]) -> str:
    value = first_present(row, ("difficulty", "difficulty_level", "level"))
    if value is None:
        metadata = row.get("metadata")
        if isinstance(metadata, Mapping):
            value = first_present(metadata, ("difficulty", "difficulty_level", "level"))
    text = _as_text(value)
    return normalize_difficulty(text) if text else "unknown"


def dataset_name(row: Mapping[str, Any]) -> str:
    value = first_present(row, ("dataset", "benchmark", "split"))
    if value is not None:
        return _as_text(value)
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        value = first_present(metadata, ("dataset", "benchmark", "split"))
        if value is not None:
            return _as_text(value)
    return "all"


def schema_text(row: Mapping[str, Any]) -> str:
    value = first_present(row, ("schema", "db_schema", "database_schema"))
    if value is not None:
        return _as_text(value)
    database = row.get("database")
    if isinstance(database, Mapping):
        value = first_present(database, ("schema", "db_schema", "database_schema"))
        if value is not None:
            return _as_text(value)
    return ""


def evidence_text(row: Mapping[str, Any]) -> str:
    value = first_present(row, ("evidence", "hint", "knowledge", "external_knowledge"))
    return _as_text(value)


def first_present(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def redact_gold_fields(row: Mapping[str, Any]) -> JsonObject:
    blocked = set(GOLD_SQL_KEYS) | {"output", "answer"}
    return {str(key): value for key, value in row.items() if str(key) not in blocked}


def normalize_difficulty(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[\s-]+", "_", text)
    aliases = {
        "extra": "extra_hard",
        "extra_hard": "extra_hard",
        "extrahard": "extra_hard",
        "extra_hard_level": "extra_hard",
    }
    return aliases.get(text, text or "unknown")


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
    return _validate_records(rows, path)


def _records_from_object(payload: Mapping[str, Any]) -> list[Any]:
    for key in ("data", "rows", "samples", "items", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [dict(payload)]


def _validate_records(rows: Iterable[Any], path: Path) -> list[JsonObject]:
    validated: list[JsonObject] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Expected JSON object at {path}, record {index}")
        validated.append(dict(row))
    return validated


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _conversation_text(row: Mapping[str, Any], *, role_index: int) -> str:
    conversations = row.get("conversations")
    if not isinstance(conversations, list) or len(conversations) <= role_index:
        return ""
    item = conversations[role_index]
    if isinstance(item, Mapping):
        return _as_text(item.get("content") or item.get("value"))
    return _as_text(item)
