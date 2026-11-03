#!/usr/bin/env bash
# Install the factory UI on Huananzhi Ubuntu 24.04, without Docker.
# Must be run locally by the normal user, never as root.
set -euo pipefail
umask 077

ROOT=/1tbdisk/PegineLab
APP="$ROOT/projects/YadroKreator"
STATE="$ROOT/factory-state"
BIND_IP="${PEGINELAB_BIND_IP:-192.168.0.100}"
VENV="$ROOT/factory-venv"
UNIT="$HOME/.config/systemd/user/peginelab-factory.service"

if [ "$(id -u)" -eq 0 ]; then
  echo "ERROR: run as regular user, not sudo/root" >&2; exit 1
fi
if [ ! -f "$APP/app.py" ] || [ ! -d "$ROOT/build/thingino-firmware/.git" ]; then
  echo "ERROR: missing PegineLab factory or pinned Thingino checkout" >&2; exit 1
fi
if ! ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$BIND_IP"; then
  echo "ERROR: $BIND_IP is not assigned to this Ubuntu host; inspect: ip -br -4 addr" >&2
  exit 1
fi
if ss -H -ltn '( sport = :62404 )' | grep -q .; then
  echo "ERROR: port 62404 is already listening. Inspect: ss -ltnp '( sport = :62404 )'" >&2
  exit 1
fi
if [ ! -e "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" || {
    echo "Install python3-venv first: sudo apt-get install python3-venv" >&2
    exit 1
  }
fi

mkdir -p "$STATE/logs" "$ROOT/build/projects/YadroKreator/cache/pip" "$(dirname "$UNIT")"
chmod 700 "$STATE" "$STATE/logs"
export PIP_CACHE_DIR="$ROOT/build/projects/YadroKreator/cache/pip"
"$VENV/bin/python" -m pip install --disable-pip-version-check -r "$APP/requirements.txt"
echo "Running dashboard tests before systemd installation..."
"$VENV/bin/python" -m unittest discover -s "$APP/tests" -p "test_*.py" -v

cat > "$UNIT" <<EOF
[Unit]
Description=PegineLab Firmware Factory — local web dashboard
After=default.target

[Service]
Type=simple
WorkingDirectory=$APP
Environment=PEGINELAB_HOME=$ROOT
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/waitress-serve --listen=$BIND_IP:62404 app:app
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=default.target
EOF

# User services and their transient child build units survive SSH logout.
sudo loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now peginelab-factory.service
echo
echo "Factory service enabled. Check:"
echo "  systemctl --user status peginelab-factory.service --no-pager"
echo "  ss -ltnp '( sport = :62404 )'"
echo
echo "Open in VPN / LAN browser: http://$BIND_IP:62404/"
echo "No web password. Isolate access with VPN/firewall if needed."
