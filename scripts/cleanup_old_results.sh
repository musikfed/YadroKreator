#!/usr/bin/env bash
# PegineLab CORE — old shared build results. Safe by default: DRY RUN.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ "$(id -u)" -eq 0 ]; then
    echo "Do not run cleanup with sudo/root; use the YadroKreator service user." >&2
    exit 2
fi
exec python3 "$SCRIPT_DIR/cleanup_legacy_builds.py" "$@"
