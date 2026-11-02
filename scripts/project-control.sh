#!/usr/bin/env bash
# YadroKreator project lifecycle: ONLY its own user systemd and labelled containers.
# Never stop systemd itself, SSH, Docker daemon, host or other projects.
set -euo pipefail
ACTION=status
if (( $# > 0 )); then ACTION="$1"; fi
WEB=peginelab-factory.service
TIMER=peginelab-factory-update.timer
TIMER_SERVICE=peginelab-factory-update.service
STATE_DIR="$HOME/.local/state/YadroKreator"
MARKER="$STATE_DIR/update-timer-was-enabled"
FAIL=0

if (( EUID == 0 )); then
    echo "ERROR: use the regular Ubuntu account, not sudo/root" >&2
    exit 2
fi
command -v systemctl >/dev/null || { echo "ERROR: systemctl missing" >&2; exit 2; }
exists() { systemctl --user cat "$1" >/dev/null 2>&1; }
active() { systemctl --user is-active --quiet "$1" 2>/dev/null; }
stop_unit() {
    if active "$1"; then
        echo "Stopping user systemd unit: $1"
        systemctl --user stop "$1" || FAIL=1
    fi
}
worker_units() {
    local output
    output="$(systemctl --user list-units --all --type=service --no-legend --no-pager --plain \
      'peginelab-t23n-*.service' 'peginelab-factory-update-*.service' \
      'peginelab-panel-*.service')" || return 1
    printf '%s\n' "$output" | awk '{
      for (i=1;i<=NF;i++) {
        if ($i ~ /^peginelab-t23n-[0-9a-f]+\.service$/ ||
            $i ~ /^peginelab-factory-update-[0-9a-f]+\.service$/ ||
            $i ~ /^peginelab-panel-(stop|restart)-[0-9a-f]+\.service$/) {
          print $i; break
        }
      }
    }' | sort -u
}
stop_workers() {
    local units unit
    if ! units="$(worker_units)"; then
        echo "ERROR: could not enumerate YadroKreator build/update units" >&2
        FAIL=1
        return
    fi
    while IFS= read -r unit; do
        if [[ -n "$unit" ]]; then stop_unit "$unit"; fi
    done <<< "$units"
}
project_container_ids() {
    local engine="$1" label ids
    for label in 'com.peginelab.project=YadroKreator' 'com.docker.compose.project=yadrokreator'; do
        if ! ids="$("$engine" ps --quiet --filter "label=$label" 2>/dev/null)"; then
            echo "WARNING: cannot inspect $engine containers; not assumed stopped" >&2
            return 1
        fi
        printf '%s\n' "$ids"
    done | sort -u
}
stop_containers() {
    local engine ids id
    for engine in docker podman; do
        command -v "$engine" >/dev/null 2>&1 || continue
        ids="$(project_container_ids "$engine")" || { FAIL=1; continue; }
        while IFS= read -r id; do
            [[ "$id" =~ ^[0-9a-f]{12,64}$ ]] || continue
            echo "Stopping $engine YadroKreator-labelled container: $id"
            "$engine" stop "$id" || FAIL=1
        done <<< "$ids"
    done
}
warn_legacy_system_service() {
    if systemctl is-active --quiet peginelab-t23n-build.service 2>/dev/null; then
        echo "WARNING: legacy SYSTEM peginelab-t23n-build.service still active!" >&2
        echo "Explicit administrator action: sudo systemctl stop peginelab-t23n-build.service" >&2
        FAIL=1
    fi
}
stop_all() {
    echo "Stopping entire YadroKreator project, including jobs and update timer..."
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
    if exists "$TIMER"; then
        if [[ "$(systemctl --user is-enabled "$TIMER" 2>/dev/null || true)" == enabled ]]; then
            printf 'enabled\n' > "$MARKER"
        else
            rm -f "$MARKER"
        fi
        systemctl --user disable --now "$TIMER" || FAIL=1
    fi
    stop_unit "$TIMER_SERVICE"
    stop_workers
    if exists "$WEB"; then
        # Disable autostart on reboot; start.sh will re-enable.
        systemctl --user disable --now "$WEB" || FAIL=1
    fi
    stop_containers
    warn_legacy_system_service
    echo "Stopped project-owned resources. Firmware files, logs and SQLite history preserved."
    if ((FAIL)); then
        echo "WARNING: some resources could not be verified/stopped; see errors above." >&2
        return 1
    fi
    echo "FULL STOP completed. Restart with: bash start.sh"
}
start_all() {
    exists "$WEB" || { echo "ERROR: missing user unit; run bash install.sh first" >&2; return 2; }
    systemctl --user enable --now "$WEB"
    if [[ -f "$MARKER" ]] && exists "$TIMER"; then
        systemctl --user enable --now "$TIMER"
        rm -f "$MARKER"
    fi
    echo "Dashboard started: http://192.168.0.100:62404/"
    echo "Stopped build jobs and containers are NOT automatically restarted."
}
show_status() {
    local unit engine label
    for unit in "$WEB" "$TIMER" "$TIMER_SERVICE"; do
        echo "$unit: $(systemctl --user is-active "$unit" 2>/dev/null || true), enabled=$(systemctl --user is-enabled "$unit" 2>/dev/null || true)"
    done
    echo "Project build/update units:"
    worker_units || true
    if systemctl is-active --quiet peginelab-t23n-build.service 2>/dev/null; then
        echo "WARNING: legacy SYSTEM peginelab-t23n-build.service ACTIVE"
    fi
    echo "Project-labelled containers:"
    for engine in docker podman; do
        command -v "$engine" >/dev/null 2>&1 || continue
        for label in 'com.peginelab.project=YadroKreator' 'com.docker.compose.project=yadrokreator'; do
            "$engine" ps --filter "label=$label" --format '{{.ID}} {{.Names}}' ||
                echo "WARNING: cannot inspect $engine" >&2
        done
    done
}
case "$ACTION" in
    start|start-all) start_all ;;
    stop|stop-all) stop_all ;;
    status) show_status ;;
    stop-panel) systemctl --user stop "$WEB" ;;
    start-panel) systemctl --user start "$WEB" ;;
    *) echo "Usage: bash scripts/project-control.sh [start|stop|status|stop-panel|start-panel]" >&2; exit 2 ;;
esac
