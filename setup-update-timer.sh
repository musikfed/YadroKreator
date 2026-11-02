#!/usr/bin/env bash
# Explicit opt-in: poll GitHub main to report updates. Never deploy without explicit consent.
set -euo pipefail
ROOT="${PEGINELAB_HOME:-/1tbdisk/PegineLab}"
APP="$ROOT/projects/YadroKreator"
UNIT_DIR="$HOME/.config/systemd/user"
case "${1:-}" in
  enable)
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT_DIR/peginelab-factory-update.service" <<EOF
[Unit]
Description=PegineLab YadroKreator GitHub update availability check
[Service]
Type=oneshot
Environment=PEGINELAB_HOME=$ROOT
ExecStart=/bin/bash $APP/deploy.sh --check
EOF
    cat > "$UNIT_DIR/peginelab-factory-update.timer" <<'EOF'
[Unit]
Description=Check YadroKreator GitHub main availability every 15 minutes (no deployment)
[Timer]
OnBootSec=3min
OnUnitActiveSec=15min
Persistent=true
[Install]
WantedBy=timers.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now peginelab-factory-update.timer
    echo "Opt-in update timer enabled. Check: systemctl --user list-timers"
    ;;
  disable)
    systemctl --user disable --now peginelab-factory-update.timer
    echo "Update timer disabled."
    ;;
  *)
    echo "Usage: bash setup-update-timer.sh enable|disable" >&2; exit 2;;
esac
