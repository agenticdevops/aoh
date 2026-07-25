#!/usr/bin/env bash
set -euo pipefail

command -v aoh >/dev/null || { echo "ERROR: aoh not found on PATH — run from this repo's venv or via 'uv run aoh skill promote ...' instead" >&2; exit 1; }

exec aoh skill promote "$@"
