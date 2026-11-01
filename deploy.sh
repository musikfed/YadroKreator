#!/usr/bin/env bash
# Git-only dashboard update. No files copied by hand, no force reset or Docker.
set -euo pipefail
umask 077
ROOT="${PEGINELAB_HOME:-/1tbdisk/PegineLab}"
APP="$ROOT/projects/YadroKreator"
VENV="$ROOT/factory-venv"
URL="https://github.com/musikfed/YadroKreator.git"
ACTION="${1:---check}"

if [ "$ACTION" != "--check" ] && [ "$ACTION" != "--apply" ]; then
  echo "Usage: bash deploy.sh [--check|--apply]" >&2; exit 2
fi
if [ "$(id -u)" -eq 0 ]; then echo "Refusing root/sudo"; exit 1; fi
[ "$(cd "$(dirname "$0")" && pwd -P)" = "$APP" ] || {
  echo "Run from $APP checkout" >&2; exit 1;
}
[ "$(git -C "$APP" rev-parse --abbrev-ref HEAD)" = "main" ] || {
  echo "Deploy only tracks YadroKreator main" >&2; exit 1;
}
[ "$(git -C "$APP" remote get-url origin)" = "$URL" ] || {
  echo "Unexpected YadroKreator remote URL" >&2; exit 1;
}
[ -z "$(git -C "$APP" status --porcelain --untracked-files=no)" ] || {
  echo "Tracked local changes exist: refusing overwrite" >&2; exit 1;
}
command -v git >/dev/null
git -C "$APP" fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
CURRENT="$(git -C "$APP" rev-parse HEAD)"
REMOTE="$(git -C "$APP" rev-parse origin/main)"
echo "Installed: $CURRENT"
echo "Available: $REMOTE"
if [ "$CURRENT" = "$REMOTE" ]; then echo "Already current"; exit 0; fi
git -C "$APP" merge-base --is-ancestor "$CURRENT" "$REMOTE" || {
  echo "Non fast-forward: refusing auto-deploy" >&2; exit 1;
}
if [ "$ACTION" = "--check" ]; then
  echo "Update available. Run: bash deploy.sh --apply"
  exit 0
fi
# Replacing the UI during compilation is unnecessary and confusing.
# The separate transient systemd build units are not stopped or restarted.
DB="$ROOT/factory-state/factory.sqlite3"
if [ -f "$DB" ]; then
  if DB="$DB" python3 - <<'PY'
import os, sqlite3, sys
db=sqlite3.connect(os.environ["DB"])
try:
    busy=db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running','stopping')").fetchone()[0]
except sqlite3.OperationalError as exc:
    sys.exit("Cannot determine build status: " + str(exc))
sys.exit(0 if busy == 0 else 1)
PY
  then :; else
    echo "A build is active (or DB unreadable). Retry deploy when idle." >&2; exit 1
  fi
fi
[ -x "$VENV/bin/python" ] || {
  echo "Missing dashboard Python venv; run bash bootstrap.sh first" >&2; exit 1
}
git -C "$APP" merge --ff-only origin/main
"$VENV/bin/python" -m pip install -r "$APP/requirements.txt"
"$VENV/bin/python" -m unittest discover -s "$APP/tests" -p "test_*.py" -v
"$VENV/bin/python" -m compileall -q "$APP/app.py" "$APP/core.py" "$APP/worker.py" "$APP/git_sources.py"
bash -n "$APP/bootstrap.sh" "$APP/deploy.sh" "$APP/install.sh"
systemctl --user restart peginelab-factory.service
systemctl --user is-active --quiet peginelab-factory.service
echo "Dashboard deployed from GitHub main: $REMOTE"
