#!/usr/bin/env bash
# One-time native Ubuntu bootstrap, no copied source files or Docker.
set -euo pipefail
umask 077
ROOT="${PEGINELAB_HOME:-/1tbdisk/PegineLab}"
APP="$ROOT/projects/YadroKreator"
THINGINO="$ROOT/build/thingino-firmware"
THINGINO_REF="9925f46f73b9c39ec8d2a65134b18c94e6fdfb97"
THINGINO_URL="https://github.com/themactep/thingino-firmware.git"

if [ "$(id -u)" -eq 0 ]; then echo "Run as an ordinary Ubuntu user, not sudo" >&2; exit 1; fi
if [ "$(cd "$(dirname "$0")" && pwd -P)" != "$APP" ]; then
  echo "Expected checked-out YadroKreator at $APP" >&2; exit 1
fi
command -v git >/dev/null || { echo "Install git first"; exit 1; }
mkdir -p "$ROOT/build" "$ROOT/projects"
if [ ! -e "$THINGINO" ]; then
  echo "Getting Thingino from upstream Git (first install only)..."
  git clone --recurse-submodules "$THINGINO_URL" "$THINGINO"
fi
if [ ! -d "$THINGINO/.git" ]; then
  echo "Thingino checkout missing or incomplete at $THINGINO" >&2; exit 1
fi
ORIGIN="$(git -C "$THINGINO" remote get-url origin)"
if [ "$ORIGIN" != "$THINGINO_URL" ]; then
  echo "Unexpected Thingino remote: $ORIGIN" >&2; exit 1
fi
if [ -n "$(git -C "$THINGINO" status --porcelain)" ]; then
  echo "Thingino contains local modifications; not resetting them" >&2; exit 1
fi
if ! git -C "$THINGINO" cat-file -e "$THINGINO_REF^{commit}" 2>/dev/null; then
  git -C "$THINGINO" fetch origin "$THINGINO_REF"
fi
git -C "$THINGINO" checkout --detach "$THINGINO_REF"
git -C "$THINGINO" submodule sync --recursive
git -C "$THINGINO" submodule update --init --recursive
[ "$(git -C "$THINGINO" rev-parse HEAD)" = "$THINGINO_REF" ]
echo "Thingino pinned at $THINGINO_REF."
# Installer starts systemd user service; WIFICAM Git source is fetched per job.
bash "$APP/install.sh"
echo "Open http://192.168.0.100:62404/ only via trusted LAN/VPN."
