# YadroKreator — full project stop/start/status

The native Huananzhi deployment uses **systemd --user**, no Docker
Compose. The old stop script stopped only the dashboard; now
`bash stop.sh` disables/stops the entire **YadroKreator-owned**
service set, including transient build workers, background update
operations, the dashboard, and opt-in GitHub timer. It does not stop
Ubuntu, systemd itself, SSH, VPN, the Docker daemon or unrelated projects.

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash stop.sh
bash scripts/project-control.sh status
bash start.sh
```

`stop.sh` disables the dashboard auto-start and update timer to keep
the project off over reboot. `start.sh` enables the dashboard, restoring
the timer only if it was previously enabled; it does not resume cancelled
builds or restart old containers. Completed artifacts, SQLite and logs
are kept intact.

Docker/Podman containers, **if any**, are stopped ONLY when explicitly
labelled `com.peginelab.project=YadroKreator` or
`com.docker.compose.project=yadrokreator`. This application normally
installs no containers. Missing Docker permissions result in a warning;
unlabelled/other-project containers are always untouched.

A legacy **system-level** `peginelab-t23n-build.service` cannot be
stopped from this unprivileged user script. If active, it is reported
and requires the explicit administrator command
`sudo systemctl stop peginelab-t23n-build.service`.

`bash scripts/project-control.sh stop-panel` is the separate
**dashboard-only** action.

Windows PowerShell (SSH into Huananzhi):
```powershell
.\stop.ps1
.\start.ps1
.\scripts\project-control.ps1 -Action status
```

The dashboard's **Stop entire project** button on Overview/System
schedules this same full stop in a detached user-systemd unit.
When a build is active, a second explicit confirmation is required.
After full stop, the website cannot start itself: use SSH and
`bash start.sh` to restore it. The existing separate GitHub
updater remains unchanged: check/apply/rollback from System, not full
STOP. Never expose dashboard port 62404 to the public Internet.

Note: arbitrary manually launched `make` processes outside the factory's
user systemd units are intentionally out of scope.
