#!/usr/bin/env bash
# Update only the YadroKreator dashboard via its tested rollback-capable updater.
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then echo "Run as regular CORE user" >&2; exit 2; fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec bash "$ROOT/deploy.sh" "${1:---check}"
