"""Read PostgreSQL schemas for text-to-SQL prompt construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PostgresSchemaConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    connect_timeout: int = 10


class PostgresSchemaLoader:
    """Load and cache DDL-like schema text from PostgreSQL catalogs."""

    def __init__(self, config: PostgresSchemaConfig):
        self.config = config
        self._cache: dict[str, str] = {}

    def load(self, schema: str) -> str:
        schema_name = str(schema or "").strip()
        if not schema_name:
            return ""
        if schema_name not in self._cache:
            self._cache[schema_name] = self._load_uncached(schema_name)
        return self._cache[schema_name]

    def _load_uncached(self, schema: str) -> str:
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: install psycopg2-binary or run "
                "`pip install -r requirements.txt`."
            ) from exc

        with psycopg2.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.database,
            user=self.config.user,
            password=self.config.password,
            connect_timeout=self.config.connect_timeout,
        ) as connection:
            connection.set_session(readonly=True)
            with connection.cursor() as cursor:
                cursor.execute(_COLUMNS_SQL, (schema,))
                column_rows = cursor.fetchall()
                cursor.execute(_CONSTRAINTS_SQL, (schema,))
                constraint_rows = cursor.fetchall()
        return _render_schema(schema, column_rows, constraint_rows)


_COLUMNS_SQL = """
SELECT
    relation.relname AS table_name,
    attribute.attname AS column_name,
    pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) AS data_type,
    attribute.attnotnull AS not_null,
    pg_catalog.pg_get_expr(default_value.adbin, default_value.adrelid) AS default_expression
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_class AS relation
    ON relation.oid = attribute.attrelid
JOIN pg_catalog.pg_namespace AS namespace
    ON namespace.oid = relation.relnamespace
LEFT JOIN pg_catalog.pg_attrdef AS default_value
    ON default_value.adrelid = relation.oid
   AND default_value.adnum = attribute.attnum
WHERE namespace.nspname = %s
  AND relation.relkind IN ('r', 'p')
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped
ORDER BY relation.relname, attribute.attnum
"""


_CONSTRAINTS_SQL = """
SELECT
    relation.relname AS table_name,
    constraint_row.conname AS constraint_name,
    pg_catalog.pg_get_constraintdef(constraint_row.oid, true) AS constraint_definition
FROM pg_catalog.pg_constraint AS constraint_row
JOIN pg_catalog.pg_class AS relation
    ON relation.oid = constraint_row.conrelid
JOIN pg_catalog.pg_namespace AS namespace
    ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = %s
  AND constraint_row.contype IN ('p', 'u', 'f', 'c')
ORDER BY relation.relname, constraint_row.conname
"""


def _render_schema(
    schema: str,
    column_rows: list[tuple[Any, ...]],
    constraint_rows: list[tuple[Any, ...]],
) -> str:
    columns_by_table: dict[str, list[str]] = {}
    for table, column, data_type, not_null, default_expression in column_rows:
        definition = f"{_quote_identifier(str(column))} {data_type}"
        if default_expression is not None:
            definition += f" DEFAULT {default_expression}"
        if not_null:
            definition += " NOT NULL"
        columns_by_table.setdefault(str(table), []).append(definition)

    constraints_by_table: dict[str, list[str]] = {}
    for table, name, definition in constraint_rows:
        rendered = f"CONSTRAINT {_quote_identifier(str(name))} {definition}"
        constraints_by_table.setdefault(str(table), []).append(rendered)

    statements: list[str] = []
    for table, columns in columns_by_table.items():
        definitions = columns + constraints_by_table.get(table, [])
        body = ",\n  ".join(definitions)
        statements.append(
            f"CREATE TABLE {_quote_identifier(schema)}.{_quote_identifier(table)} (\n"
            f"  {body}\n"
            ");"
        )
    return "\n\n".join(statements)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
