#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}/extsql_bench/src${PYTHONPATH:+:${PYTHONPATH}}"

PROMPT="${PROMPT:-postgres}"
ORACLE="${ORACLE:-false}"

if [[ "${PROMPT}" == *.txt ]]; then
  echo "PROMPT must not include the .txt extension: ${PROMPT}" >&2
  exit 2
fi
if [[ "${ORACLE}" == "true" ]]; then
  PROMPT="${PROMPT}_doc"
elif [[ "${ORACLE}" != "false" ]]; then
  echo "ORACLE must be true or false: ${ORACLE}" >&2
  exit 2
fi

python -m inference.inference \
  --llm-config "${PROJECT_ROOT}/config/llm.yaml" \
  --db-config "${PROJECT_ROOT}/config/database.yaml" \
  --prompt-template "${PROJECT_ROOT}/prompts/${PROMPT}.txt" \
  "$@"
