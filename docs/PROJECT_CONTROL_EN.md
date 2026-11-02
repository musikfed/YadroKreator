# YadroKreator dashboard: start / stop / status

The web dashboard is a user-systemd unit named `peginelab-factory.service`
on the Huananzhi Ubuntu host, port 62404. Scripts here do NOT stop the
Ubuntu machine, Docker, VPN/SSH, or separate firmware build worker units.

Linux on Huananzhi (same non-root user as `install.sh`):

```bash
bash start.sh
bash stop.sh
bash scripts/project-control.sh status
```

Windows PowerShell (SSH key access to that Linux user required):

```powershell
.\start.ps1
.\stop.ps1
.\scripts\project-control.ps1 -Action status
```

Optional `-Server 'user@192.168.0.100'` overrides the SSH target.
Stopping the dashboard removes the website; it cannot restart itself.
Stop any active firmware build job **using its own job Stop button** before
stopping the dashboard, if you actually intend to cancel that build.
Stopping the dashboard alone does not cancel a running systemd build unit.
No SSH passwords or tokens are stored by these scripts.

## Web controls (Overview and System)

The overview now shows live user-systemd service status, **Restart dashboard**, **Stop dashboard**, and a shortcut to the existing **System → Check updates → Update dashboard** workflow. Update is an actual fast-forward of the installed Git `main` checkout on Huananzhi, with tests, rollback and automatic service restart; it is not a separate unverified `git reset` route. Stop/restart POSTs require trusted LAN/VPN network access, same-origin and a custom action header. They never terminate build jobs, the host, VPN or SSH. Stopping is disabled while any build is running. The **Start (SSH)** control is intentionally disabled while the site is online: after stop the site cannot execute its own start action; use `bash start.sh` from the server or Windows SSH. Installing GitHub changes does not happen automatically after a PR merge.
