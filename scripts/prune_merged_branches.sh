#!/usr/bin/env bash
# PegineLab CORE · no sudo, no reset. Default is a read-only preview.
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
  echo "Run as the normal Huananzhi service user, never root." >&2
  exit 2
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "$ROOT/prune_merged_branches.py" "$@"
