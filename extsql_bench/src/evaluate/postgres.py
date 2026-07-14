"""PostgreSQL execution helpers for SQL benchmark evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    connect_timeout: int = 10
    statement_timeout_ms: int = 60000
    search_path: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    rows: list[tuple[Any, ...]]
    elapsed_sec: float
    error: str = ""
    error_type: str = ""


def execute_sql(sql_text: str, config: PostgresConfig) -> ExecutionResult:
    if not sql_text or not sql_text.strip():
        return ExecutionResult(
            status="empty_sql",
            rows=[],
            elapsed_sec=0.0,
            error="SQL is empty",
            error_type="EmptySQL",
        )

    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: install psycopg2-binary or run `pip install -r requirements.txt`."
        ) from exc

    conn = None
    cursor = None
    started = time.perf_counter()
    try:
        conn = psycopg2.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.user,
            password=config.password,
            connect_timeout=config.connect_timeout,
            options=f"-c statement_timeout={config.statement_timeout_ms}",
        )
        conn.autocommit = True
        cursor = conn.cursor()
        if config.search_path:
            cursor.execute(_set_search_path_sql(config.search_path))
        cursor.execute(sql_text)
        rows = cursor.fetchall() if cursor.description is not None else []
        elapsed = time.perf_counter() - started
        return ExecutionResult(status="ok", rows=list(rows), elapsed_sec=elapsed)
    except Exception as exc:  # noqa: BLE001 - preserve DB driver error text
        elapsed = time.perf_counter() - started
        return ExecutionResult(
            status=_classify_error(exc),
            rows=[],
            elapsed_sec=elapsed,
            error=str(exc),
            error_type=type(exc).__name__,
        )
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _classify_error(error: Exception) -> str:
    message = str(error).lower()
    if "statement timeout" in message or "canceling statement due to statement timeout" in message:
        return "timeout"
    return "execution_error"


def _set_search_path_sql(search_path: str) -> str:
    parts = [part.strip() for part in search_path.split(",") if part.strip()]
    if not parts:
        return "SET search_path TO public"
    quoted = ", ".join(_quote_identifier(part) for part in parts)
    return f"SET search_path TO {quoted}"


def _quote_identifier(identifier: str) -> str:
    if identifier == "$user":
        return identifier
    return '"' + identifier.replace('"', '""') + '"'
