#!/usr/bin/env bash
# Update only the separate WIFICAM T23N Git source checkout.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec bash "$SCRIPT_DIR/sync_core_projects.sh" --project wificam_T23N "$@"
