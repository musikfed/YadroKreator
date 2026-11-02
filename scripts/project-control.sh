#!/usr/bin/env bash
# Manage ONLY the installed PegineLab dashboard user-unit.
# No sudo, no Docker daemon, no build cancellation, no reboot.
set -euo pipefail
ACTION="${1:-status}"
UNIT=peginelab-factory.service
if [[ "$(id -u)" == 0 ]]; then
  echo "ERROR: use the Ubuntu user who installed YadroKreator, not root/sudo" >&2
  exit 2
fi
command -v systemctl >/dev/null || { echo "ERROR: Linux systemd user manager required" >&2; exit 2; }
if ! systemctl --user cat "$UNIT" >/dev/null 2>&1; then
  echo "ERROR: $UNIT is not installed for this user. Use bash install.sh on Huananzhi first." >&2
  exit 2
fi
case "$ACTION" in
  start)
    systemctl --user start "$UNIT"
    systemctl --user is-active --quiet "$UNIT" || {
      systemctl --user status "$UNIT" --no-pager || true; exit 1; }
    echo "YadroKreator dashboard started: http://192.168.0.100:62404/"
    ;;
  stop)
    # Does NOT stop independently-running peginelab-build-* transient units.
    systemctl --user stop "$UNIT"
    if systemctl --user is-active --quiet "$UNIT"; then
      echo "ERROR: dashboard service is still active" >&2; exit 1
    fi
    echo "YadroKreator dashboard stopped. Background build units are NOT cancelled."
    echo "Restart from SSH/Ubuntu using bash start.sh; the stopped webpage cannot restart itself."
    ;;
  status)
    systemctl --user status "$UNIT" --no-pager || true
    echo "NOTE: build worker services are separate and may continue when dashboard is stopped."
    ;;
  *)
    echo "Usage: bash scripts/project-control.sh [start|stop|status]" >&2
    exit 2
    ;;
esac
