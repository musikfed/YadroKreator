# Git-based deployments and source-pinned camera builds

## Initial installation on Huananzhi Ubuntu 24.04

As an ordinary user (not sudo), once:

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip make gcc g++ curl \
  e2fsprogs dosfstools fdisk lzop unzip rsync ccache
mkdir -p /1tbdisk/PegineLab/projects
git clone https://github.com/musikfed/YadroKreator.git /1tbdisk/PegineLab/projects/YadroKreator
cd /1tbdisk/PegineLab/projects/YadroKreator
bash bootstrap.sh
```

Bootstrap pins upstream Thingino at `9925f46f73b9c39ec8d2a65134b18c94e6fdfb97`
and installs the Flask/Waitress dashboard as a systemd user service.
It does not overwrite a locally modified Thingino checkout. Buildroot might
need additional Ubuntu packages; inspect the build log.

## Build the exact WIFICAM Git branch

Open `http://192.168.0.100:62404/` over a trusted LAN/VPN and choose
**Builds → mymarrchWFcam → New Build**. Every run fetches the allowlisted
`musikfed/wificam_T23N` branch directly from GitHub, records a SHA,
creates a detached per-job Git worktree, and builds in it. No manual copy,
branch switching or `git reset --hard` in an existing checkout.

Source cache: `/1tbdisk/PegineLab/build/git-cache/wificam_T23N.git`.
Worktrees and output:
`/1tbdisk/PegineLab/build/jobs/<job-id>/wificam_T23N/`.
Historical `mymarrchWFcam` writes its candidate under `Thingino/`
**inside its isolated job directory**; newer `main` normally writes
`out/candidate-sd/`. The original `0.1_test` baseline is untouched.
If `projects/wificam_T23N/local/wifi.env` exists, it is copied securely
(with 0600 permissions) to the isolated worktree; never published.
The factory forces `PUBLISH=0` and does not flash SD media or download
firmware over HTTP.

New firmware is NOT hardware-verified until SD boot, SSH, UI :8090, CGI,
video, PTZ and recovery have been tested on the actual T23N.

## Update YadroKreator itself from GitHub

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash deploy.sh --check
bash deploy.sh --apply
```

The update requires a clean `main` checkout, the expected canonical origin,
a fast-forward, and zero active build jobs. It installs dependencies,
runs tests, then restarts **only** the dashboard user service.
Optional opt-in 15-minute systemd timer:

```bash
bash setup-update-timer.sh enable
bash setup-update-timer.sh disable
```

Auto-update is disabled by default. Only allow reviewed, CI-tested code
onto `main` before enabling unattended update. This workflow is a code
implementation, not evidence that the user's private server is running.
Port 62404 must be restricted to trusted LAN/VPN clients because the UI
has no built-in password and can launch build processes.
