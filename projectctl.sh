#!/usr/bin/env bash
# PegineLab YadroKreator control. Only its systemd USER service is affected.
# Firmware builds run in separate transient units and are NOT stopped here.
set -euo pipefail
UNIT=peginelab-factory.service
ACTION="${1:-status}"
case "$ACTION" in start|stop|restart|status|enable|disable) ;; *)
  echo "Usage: bash projectctl.sh {start|stop|restart|status|enable|disable}" >&2
  exit 2 ;;
esac
if [ "$(id -u)" = 0 ]; then
  echo "ERROR: run as regular Ubuntu user that installed YadroKreator; no sudo." >&2
  exit 2
fi
command -v systemctl >/dev/null || { echo "ERROR: systemctl not available; this project runs on Ubuntu systemd." >&2; exit 2; }
if ! systemctl --user show "$UNIT" -p LoadState --value 2>/dev/null | grep -Fxq loaded; then
  echo "ERROR: $UNIT not installed for this user. On Huananzhi first run bash install.sh." >&2
  exit 3
fi
case "$ACTION" in
  stop)
    echo "Stopping ONLY YadroKreator dashboard (TCP 62404)."
    echo "Existing build jobs have their own systemd units and keep running."
    systemctl --user stop "$UNIT" ;;
  start)
    systemctl --user start "$UNIT" ;;
  restart)
    systemctl --user restart "$UNIT" ;;
  status)
    systemctl --user --no-pager --full status "$UNIT" ;;
  enable)
    systemctl --user enable "$UNIT"
    echo "Enabled at next user-session boot; run start separately if needed." ;;
  disable)
    echo "Disabling auto-start; current service is NOT stopped. Use stop separately."
    systemctl --user disable "$UNIT" ;;
esac
if [ "$ACTION" != status ]; then
  echo
  systemctl --user is-active "$UNIT" || true
  echo "Dashboard: http://192.168.0.100:62404/ (only if service is active)"
fi
