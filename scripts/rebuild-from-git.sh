#!/usr/bin/env bash
# SSH-only YadroKreator rebuild. Does not touch Docker, camera or ACHEWIW.
set -euo pipefail
umask 077
ROOT=/1tbdisk/PegineLab
APP="$ROOT/projects/YadroKreator"
DB="$ROOT/factory-state/factory.sqlite3"
VENV="$ROOT/factory-venv"
MODE=--check
CLEAN=no
if (( $# > 0 )); then MODE="$1"; fi
if (( $# > 1 )); then [[ "$2" == --clean-cache ]] || exit 2; CLEAN=yes; fi
(( $# <= 2 )) && [[ "$MODE" == --check || "$MODE" == --apply ]] || {
  echo "Usage: bash scripts/rebuild-from-git.sh [--check|--apply] [--clean-cache]" >&2; exit 2;
}
[[ "$(id -u)" != 0 ]] || { echo "Run without sudo" >&2; exit 2; }
[[ -d "$APP/.git" && ! -L "$APP" ]] || { echo "Expected factory checkout missing" >&2; exit 2; }
cd "$APP"
[[ "$(git rev-parse --show-toplevel)" == "$APP" && "$(git branch --show-current)" == main ]] || {
  echo "Expected YadroKreator/main checkout" >&2; exit 2;
}
case "$(git remote get-url origin)" in
  https://github.com/musikfed/YadroKreator|https://github.com/musikfed/YadroKreator.git|git@github.com:musikfed/YadroKreator|git@github.com:musikfed/YadroKreator.git) ;;
  *) echo "Untrusted Git origin" >&2; exit 2 ;;
esac
[[ -z "$(git status --porcelain)" ]] || {
  echo "Working tree is dirty; refusing destructive reset/clean" >&2
  git status --short
  exit 3
}
python3 - "$DB" "$MODE" <<'PY'
import sqlite3,sys
from pathlib import Path
p=Path(sys.argv[1])
if not p.exists(): raise SystemExit(0)
if p.is_symlink(): raise SystemExit("Factory DB must not be a symlink")
with sqlite3.connect(f"file:{p}?mode=ro",uri=True,timeout=10) as db:
    if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
        raise SystemExit("Factory SQLite corrupt: refusing update")
    count=db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    busy=db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running','stopping')").fetchone()[0]
    print("Factory SQLite jobs:",count,"active:",busy)
    if sys.argv[2]=="--apply" and busy: raise SystemExit("Active builds: do not rebuild")
PY
if [[ "$MODE" == --check ]]; then
  echo "DRY RUN: no changes to services, caches, SQLite or containers."
  bash deploy.sh --check
  exit 0
fi
if [[ -f "$DB" ]]; then
  python3 - "$DB" "$ROOT/factory-state/backups" <<'PY'
from pathlib import Path
from datetime import datetime,timezone
import sqlite3,os,sys,uuid
db=Path(sys.argv[1]);directory=Path(sys.argv[2])
if directory.is_symlink(): raise SystemExit("Unsafe SQLite backup path")
directory.mkdir(mode=0o700,parents=True,exist_ok=True)
target=directory/("factory-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8]+".sqlite3")
fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
try:
    with sqlite3.connect(f"file:{db}?mode=ro",uri=True) as src,sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as saved:
        if saved.execute("PRAGMA quick_check").fetchone()[0]!="ok": raise RuntimeError("Backup failed integrity check")
except Exception:
    target.unlink(missing_ok=True);raise
print("Factory SQLite backup:",target)
PY
fi
echo "1/4 GitHub fast-forward via existing safe updater"
bash deploy.sh --apply
echo "2/4 Verify dependencies and full test suite"
"$VENV/bin/python" -m pip install --disable-pip-version-check -r "$APP/requirements.txt"
"$VENV/bin/python" -m unittest discover -s "$APP/tests" -p 'test_*.py' -q
if [[ "$CLEAN" == yes ]]; then
  echo "3/4 Clear ONLY project-specific pip cache and Python bytecode"
  python3 - "$APP" "$ROOT/build/projects/YadroKreator/cache/pip" <<'PY'
from pathlib import Path
import shutil,sys
app=Path(sys.argv[1]);cache=Path(sys.argv[2])
if str(app)!="/1tbdisk/PegineLab/projects/YadroKreator" or str(cache)!="/1tbdisk/PegineLab/build/projects/YadroKreator/cache/pip": raise SystemExit("Invalid cache path")
if cache.is_symlink():raise SystemExit("Cache symlink refused")
if cache.is_dir():shutil.rmtree(cache)
for folder in [app,app/"scripts",app/"tests"]:
    p=folder/"__pycache__"
    if p.is_symlink(): raise SystemExit("Cache symlink refused")
    if p.is_dir():shutil.rmtree(p)
print("Only YadroKreator caches cleared")
PY
else
  echo "3/4 Cache preserved (use --clean-cache to clear only YadroKreator)"
fi
echo "4/4 Restart ONLY factory web user unit and verify API"
systemctl --user restart peginelab-factory.service
curl -fsS --max-time 10 http://192.168.0.100:62404/api/panel/service >/dev/null
git rev-parse --short HEAD
echo "Factory ready. SQLite, Git images, build history, Ollama, Docker and other projects untouched."
