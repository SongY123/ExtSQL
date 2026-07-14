#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}/extsql_bench/src${PYTHONPATH:+:${PYTHONPATH}}"

python -m evaluate.evaluate \
  --db-config "${PROJECT_ROOT}/config/database.yaml" \
  "$@"
