#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}/extsql_bench/src${PYTHONPATH:+:${PYTHONPATH}}"

METRIC="all"
if [[ $# -gt 0 ]]; then
  case "$1" in
    ex|ves|all)
      METRIC="$1"
      shift
      ;;
  esac
fi

python -m evaluate.evaluate \
  --db-config "${PROJECT_ROOT}/config/database.yaml" \
  --metric "${METRIC}" \
  "$@"
