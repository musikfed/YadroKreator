#!/usr/bin/env bash
# One-time SSH recovery for pre-stepper YadroKreator deployments.
# Intended to be loaded from the approved origin/main via git show.
# Never touches WIFICAM, Thingino, SD cards or recorded firmware jobs.
set -Eeuo pipefail
umask 077
ROOT="${PEGINELAB_HOME:-/1tbdisk/PegineLab}"
APP="$ROOT/projects/YadroKreator"
VENV="$ROOT/factory-venv/bin/python"
STATE="$ROOT/factory-state"
cd "$APP"
[ "$(id -u)" -ne 0 ] || { echo "Do not run as root" >&2; exit 1; }
[ "$(git symbolic-ref --short HEAD)" = "main" ] || { echo "Requires main checkout" >&2; exit 1; }
[ "$(git remote get-url origin)" = "https://github.com/musikfed/YadroKreator.git" ] || {
  echo "Unexpected Git origin" >&2; exit 1;
}
[ -z "$(git status --porcelain --untracked-files=no)" ] || {
  echo "Local tracked modifications: refusing update" >&2; exit 1;
}
[ -x "$VENV" ] || { echo "Python venv missing" >&2; exit 1; }
python3 - "$STATE" <<'PY'
import json, sqlite3, sys
from pathlib import Path
root=Path(sys.argv[1])
file=root/"updates.json"
if file.is_file() and json.loads(file.read_text()).get("phase") in ("queued","running"):
    raise SystemExit("Update still active: wait for completion before recovery")
db=root/"factory.sqlite3"
if db.exists():
    with sqlite3.connect(db) as connection:
        if connection.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone():
            raise SystemExit("Build still active: refusing dashboard recovery")
PY
BEFORE="$(git rev-parse HEAD)"
TARGET="$(git rev-parse --verify refs/remotes/origin/main)"
git merge-base --is-ancestor "$BEFORE" "$TARGET" || {
  echo "Not a fast-forward: refusing rewrite" >&2; exit 1;
}
echo "YadroKreator recovery: $BEFORE -> $TARGET"
echo "External Thingino and WIFICAM builds are not touched."
revert_on_failure() {
  rc=$?
  trap - ERR
  if [ "$BEFORE" != "$TARGET" ] && [ "$(git rev-parse HEAD)" = "$TARGET" ] &&
     [ -z "$(git status --porcelain --untracked-files=no)" ]; then
    echo "Recovery failed. Restoring original dashboard Git SHA..."
    git reset --hard "$BEFORE" || true
    systemctl --user restart peginelab-factory.service || true
  fi
  exit "$rc"
}
trap revert_on_failure ERR
if [ "$BEFORE" != "$TARGET" ]; then git merge --ff-only "$TARGET"; fi
"$VENV" -m pip install --disable-pip-version-check -r requirements.txt
# The important difference from legacy updater: tests run with cwd=$APP.
"$VENV" -m unittest discover -s tests -p "test_*.py" -v
"$VENV" -m compileall -q app.py core.py worker.py git_sources.py \
  update_manager.py artifact_checks.py build_metrics.py download_access.py
bash -n install.sh deploy.sh bootstrap.sh setup-update-timer.sh
systemctl --user restart peginelab-factory.service
systemctl --user is-active --quiet peginelab-factory.service
python3 - "$BEFORE" "$TARGET" <<'PY'
import sys, uuid
from update_manager import locked, _read, _write, append_log, stamp, STEP_ORDER
before, target = sys.argv[1:]
operation=uuid.uuid4().hex
with locked():
    state=_read()
    state.update(phase="success", action="apply", operation=operation,
                 message="SSH recovery completed: dashboard tested and restarted",
                 remote_sha=target, installed_sha=target, can_fast_forward=True,
                 step="done", step_index=len(STEP_ORDER)-1,
                 step_total=len(STEP_ORDER)-1, failed_step="",
                 updated_at=stamp(), finished_at=stamp(), checked_at=stamp())
    if before != target:
        state.update(rollback_sha=before, rollback_from=target)
    _write(state)
append_log(operation, "SUCCESS: checked out "+target[:12]+"; dashboard running")
PY
trap - ERR
echo "SUCCESS: YadroKreator is now at $TARGET; systemd service active."
echo "Open http://192.168.0.100:62404/#system and refresh the browser."
