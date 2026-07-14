"""Typed YAML/JSON configuration loading for ExtSQL commands."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class DatabaseSettings:
    connection_type: str
    host: str
    port: int
    database: str
    user: str
    password: str
    connect_timeout: int
    statement_timeout: float
    search_path: str = ""


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout: float
    retries: int
    retry_sleep: float
    system_prompt: str = ""


def load_database_settings(path: str | Path) -> DatabaseSettings:
    config = load_config_mapping(path, label="database")
    connection_type = _text(config.get("type") or config.get("connection_type"))
    if connection_type.lower() not in {"postgresql", "postgres"}:
        raise ValueError(
            f"Unsupported database type {connection_type!r}; only postgresql is supported."
        )

    port = _positive_int(config.get("port"), "database.port")
    if port > 65535:
        raise ValueError("database.port must be at most 65535")

    return DatabaseSettings(
        connection_type="postgresql",
        host=_required_text(config, "host", "database"),
        port=port,
        database=_required_text(config, "database", "database"),
        user=_required_text(config, "user", "database"),
        password=_text(config.get("password")),
        connect_timeout=_positive_int(
            config.get("connect_timeout", 10),
            "database.connect_timeout",
        ),
        statement_timeout=_positive_float(
            config.get("statement_timeout", 60),
            "database.statement_timeout",
        ),
        search_path=_text(config.get("search_path")),
    )


def load_llm_settings(path: str | Path) -> LLMSettings:
    config = load_config_mapping(path, label="LLM")
    provider = _required_text(config, "provider", "LLM").lower()
    if provider != "openai_compatible":
        raise ValueError(
            f"Unsupported LLM provider {provider!r}; only openai_compatible is supported."
        )

    api_key = _text(config.get("api_key"))
    api_key_env = _text(config.get("api_key_env"))
    if not api_key and api_key_env:
        api_key = os.getenv(api_key_env, "")
        # EMPTY is the conventional non-secret key used by local OpenAI-
        # compatible servers such as vLLM.
        if not api_key and api_key_env == "EMPTY":
            api_key = "EMPTY"
        elif not api_key:
            raise ValueError(
                f"Environment variable {api_key_env!r} configured by "
                "LLM.api_key_env is not set."
            )

    return LLMSettings(
        provider=provider,
        model=_required_text(config, "model", "LLM"),
        base_url=_required_text(config, "base_url", "LLM"),
        api_key=api_key or "EMPTY",
        temperature=float(config.get("temperature", 0.0)),
        max_tokens=_positive_int(config.get("max_tokens", 512), "LLM.max_tokens"),
        timeout=_positive_float(config.get("timeout", 120), "LLM.timeout"),
        retries=_positive_int(config.get("retries", 3), "LLM.retries"),
        retry_sleep=_nonnegative_float(
            config.get("retry_sleep", 2.0),
            "LLM.retry_sleep",
        ),
        system_prompt=_text(config.get("system_prompt")),
    )


def load_config_mapping(path: str | Path, *, label: str) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"{label} config does not exist: {source}")

    with source.open("r", encoding="utf-8") as handle:
        if source.suffix.lower() == ".json":
            payload = json.load(handle)
        else:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError(
                    "Missing dependency: install PyYAML or run "
                    "`pip install -r requirements.txt`."
                ) from exc
            payload = yaml.safe_load(handle)

    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected a mapping in {label} config: {source}")
    return {str(key): value for key, value in payload.items()}


def _required_text(config: Mapping[str, Any], key: str, label: str) -> str:
    value = _text(config.get(key))
    if not value:
        raise ValueError(f"Missing required field {label}.{key}")
    return value


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return parsed


def _positive_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return parsed


def _nonnegative_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if parsed < 0:
        raise ValueError(f"{field} must be nonnegative")
    return parsed
