#!/usr/bin/env bash
# Same safe update engine as the web UI; standalone from any SSH session.
set -euo pipefail
umask 077
ACTION="${1:---check}"
case "$ACTION" in --check|--apply|--rollback) ;; *)
  echo "Usage: bash deploy.sh [--check|--apply|--rollback]" >&2; exit 2;; esac
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
cd "$DIR"
export PEGINELAB_HOME="${PEGINELAB_HOME:-/1tbdisk/PegineLab}"
python3 - "$ACTION" <<'PY'
import sys
from update_manager import start, perform, view

def execute(action, expected=""):
    operation = start(action, expected)["operation"]
    perform(operation)
    result = view()
    print(action, result.get("phase"), result.get("message", ""))
    if result.get("phase") != "success":
        raise SystemExit(1)
    return result

action = sys.argv[1]
if action == "--check":
    execute("check")
elif action == "--apply":
    result = execute("check")
    if result.get("update_available"):
        execute("apply", result["remote_sha"])
    else:
        print("No safe new Git main version to install")
else:
    execute("rollback")
PY
