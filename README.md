## SQL Inference and Evaluation

Install dependencies first:

```bash
pip install -r requirements.txt
```

Runtime configuration is stored in two YAML files:

- `config/llm.yaml`: provider, model, endpoint, API-key environment variable,
  generation parameters, and request timeout.
- `config/database.yaml`: PostgreSQL type, address, credentials, database, and
  connection/statement timeouts.

Both files are parsed and validated by Python. The shell scripts only pass
their paths to the corresponding Python modules.

Run inference with an OpenAI-compatible API. The backend can be OpenAI, Claude behind an OpenAI-compatible gateway, or a vLLM OpenAI-compatible endpoint.
The shell entry invokes the `inference.inference` Python module.

```bash
bash scripts/inference.sh \
  --input dataset/pilot_annotations.json \
  --output results/predictions.json
```

The script passes `config/llm.yaml` and `config/database.yaml` to Python. It
does not parse model or database settings in shell. To use other files, pass
their paths as trailing overrides:

```bash
bash scripts/inference.sh \
  --input dataset/pilot_annotations.json \
  --output results/predictions.json \
  --llm-config /path/to/llm.yaml \
  --db-config /path/to/database.yaml
```

The default prompt template is:

```text
prompts/postgres.txt
```

`scripts/inference.sh` defines `PROMPT=postgres` without a file extension and
`ORACLE=false` by default. Set `ORACLE=true` to append `_doc` and select
`prompts/postgres_doc.txt`:

```bash
ORACLE=true bash scripts/inference.sh \
  --input dataset/pilot_annotations.json \
  --output results/predictions_doc.json
```

The regular template uses `{db_schema}` and `{question}`. The `_doc` template
also uses `{oracle_function_and_operator}`, populated from `sql_objects` entries
whose type is `function` or `operator`. Benchmark Evidence remains excluded.
`--prompt-template` can still override the path passed by the shell script.

When an input row does not contain an embedded schema and no `--schema-dir` is
provided, inference reads the schema from `postgis_db` through PostgreSQL. The
row's `database.db_id` is used as the schema name; for
`dataset/pilot_annotations.json` this is `nyc_workshop`.

Run PostgreSQL execution evaluation:

```bash
bash scripts/evaluate.sh \
  --input dataset/pilot_annotations.json \
  --predictions results/predictions.json \
  --ves-repeats 3 \
  --details-output results/eval_details.json
```

`evaluate.sh` passes `config/database.yaml` to the Python evaluator. A custom
database config can be selected with `--db-config /path/to/database.yaml`.

Database settings are defined in `config/database.yaml`; LLM settings are
defined in `config/llm.yaml`. During evaluation each row's `database.db_id`
becomes the active PostgreSQL schema before its SQL runs.

The prediction file format is:

```json
[
  {
    "id": "1",
    "sql": "SELECT 1;"
  }
]
```

The evaluator connects to PostgreSQL, executes predicted SQL and gold SQL from the input JSON, compares execution results, and prints EX/VES metrics by `difficulty` plus the overall `all` metrics.
