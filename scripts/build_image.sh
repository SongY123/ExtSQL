#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
image_dir="${repo_root}/image"

image_tag="${IMAGE_TAG:-extsql-postgres:18.4}"
pg_search_version="${PG_SEARCH_VERSION:-0.24.1}"
pg_jsonschema_version="${PG_JSONSCHEMA_VERSION:-0.3.4}"
docker_build_args=()

usage() {
  cat <<'EOF'
Usage: scripts/build_image.sh [options] [docker build options]

Build the ExtSQL PostgreSQL extension image.

Options:
  -t, --tag TAG     Image tag to build. Defaults to extsql-postgres:18.4.
  -h, --help        Show this help message.

Environment variables:
  IMAGE_TAG                 Default image tag when -t/--tag is not provided.
  PG_SEARCH_VERSION         ParadeDB pg_search version. Defaults to 0.24.1.
  PG_JSONSCHEMA_VERSION     Supabase pg_jsonschema version. Defaults to 0.3.4.

Examples:
  scripts/build_image.sh
  scripts/build_image.sh --tag extsql-postgres:18.4-dev --no-cache
  PG_SEARCH_VERSION=0.24.1 scripts/build_image.sh --platform linux/amd64
EOF
}

while (($#)); do
  case "$1" in
    -t|--tag)
      if (($# < 2)); then
        echo "Missing value for $1" >&2
        exit 2
      fi
      image_tag="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      docker_build_args+=("$@")
      break
      ;;
    *)
      docker_build_args+=("$1")
      shift
      ;;
  esac
done

if [[ ! -f "${image_dir}/Dockerfile" ]]; then
  echo "Dockerfile not found: ${image_dir}/Dockerfile" >&2
  exit 1
fi

docker build \
  --file "${image_dir}/Dockerfile" \
  --tag "${image_tag}" \
  --build-arg "PG_SEARCH_VERSION=${pg_search_version}" \
  --build-arg "PG_JSONSCHEMA_VERSION=${pg_jsonschema_version}" \
  "${docker_build_args[@]}" \
  "${image_dir}"
