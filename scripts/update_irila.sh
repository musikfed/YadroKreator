#!/usr/bin/env bash
# Update only the separate Irila Baikal Git source checkout.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec bash "$SCRIPT_DIR/sync_core_projects.sh" --project Irila_baikal_v1.0 "$@"
