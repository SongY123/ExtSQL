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

Each prediction record includes the generated SQL plus inference measurements:

```json
{
  "id": "1",
  "sql": "SELECT 1;",
  "difficulty": "easy",
  "input_tokens": 1200,
  "output_tokens": 80,
  "total_tokens": 1280,
  "inference_time_ms": 1534.27
}
```

`input_tokens`, `output_tokens`, and `total_tokens` come from the
OpenAI-compatible response `usage` object. If the backend does not return
usage, these fields are `null` rather than estimated. `total_tokens` is
calculated as input plus output tokens when both values are available.
`inference_time_ms` measures from the first API request until the complete
response is received, including retry delays when retries occur. After all
rows finish, inference prints average input, output, and total tokens plus
average inference time grouped by `difficulty` and for `all` rows.

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

Run PostgreSQL execution evaluation. The optional first argument selects
`ex`, `ves`, or `all`; if omitted, it defaults to `all`:

```bash
bash scripts/evaluate.sh all \
  --input dataset/pilot_annotations.json \
  --predictions results/predictions.json \
  --details-output results/eval_details.json
```

Evaluate only one metric:

```bash
# EX only (does not run the repeated VES timing loop)
bash scripts/evaluate.sh ex \
  --input dataset/pilot_annotations.json \
  --predictions results/predictions.json

# VES only
bash scripts/evaluate.sh ves \
  --input dataset/pilot_annotations.json \
  --predictions results/predictions.json \
  --ves-repeats 10
```

The equivalent Python option is `--metric {ex,ves,all}`. The shell script also
accepts this option directly; the positional form above is provided for
convenience.

`evaluate.sh` passes `config/database.yaml` to the Python evaluator. A custom
database config can be selected with `--db-config /path/to/database.yaml`.

Database settings are defined in `config/database.yaml`; LLM settings are
defined in `config/llm.yaml`. During evaluation each row's `database.db_id`
becomes the active PostgreSQL schema before its SQL runs. Every evaluation
connection executes `SET search_path TO "<db_id>", "public"`, so the current
schema always takes precedence and `public` remains the fallback. When
`db_id` is already `public`, the evaluator sets only `search_path TO public`
and does not add it twice.

The metric implementation follows BIRD's official `evaluation.py` and
`evaluation_ves.py`:

- **EX** compares `set(predicted_rows) == set(gold_rows)`. Row order and
  duplicate rows are ignored, while column order is preserved. A SQL execution
  error or timeout scores 0.
- **VES** first applies the same EX check. Correct samples are timed in paired
  order (`predicted`, then `gold`) for every repetition. Each repetition
  produces `gold_time / predicted_time`; ratios outside the strict
  `mean ± 3 * population_standard_deviation` interval are removed. The
  per-sample score is `sqrt(mean(filtered_ratios)) * 100`; incorrect, timed-out,
  or failed samples score 0. Dataset VES is the mean of per-sample scores over
  all samples, including zeros.

`--ves-repeats` defaults to 10 and is used only by `ves` and `all`. Set it to
100 when reproducing BIRD's original repetition count.
Timing measures SQL execution itself, excluding connection setup, schema setup,
and result fetching. `connect_timeout` and the per-query
`statement_timeout` (seconds) remain configurable in `config/database.yaml`.
The details output records raw and filtered timing ratios as
`ves_raw_ratios` and `ves_filtered_ratios` for auditing. The official BIRD EX
result is stored as `ex`; only the field name is simplified, while the BIRD
evaluation logic remains unchanged.
For VES, every repeated predicted and gold SQL execution time is recorded in
`pred_time_secs` and `gold_time_secs`. Their arithmetic means are retained in
`pred_time_sec` and `gold_time_sec`.

The prediction file format is:

```json
[
  {
    "id": "1",
    "sql": "SELECT 1;"
  }
]
```

The evaluator connects to PostgreSQL, executes predicted SQL and gold SQL from
the input JSON, and prints the selected metrics by `difficulty` plus the
overall `all` row.
