# Safe code modifications and release process

Keep **YadroKreator** (Flask/Waitress API, worker, UI, tests and diagrams) separate from **wificam_T23N** (camera Web UI, Thingino overlays, kernel/driver configuration, SD image assembler). \`release/0.1_test\` is a hardware-booted backup image with older Web UI bugs, not a production release.

## Responsibilities / edit guardrails

- \`templates/index.html\` / \`static/*\`: appearance and controls; no arbitrary shell or private image downloads.
- \`build_metrics.py\`: elapsed time and *estimated*, not measured, compile progress.
- \`artifact_checks.py\`: profile-specific **read-only** structural verification. Preserve T23N LBA34 / FAT16 p1 LBA2048 / ext4 p2 LBA34816 unless a different, hardware-proven board format is introduced as a **new validator**.
- \`git_sources.py\`: trusted repositories, branch allowlist and detached immutable Git worktrees; never arbitrary client URLs.
- \`worker.py\`: pinned SHA build orchestration, \`PUBLISH=0\`, isolated systemd jobs.
- \`core.py\`: SQLite migrations must preserve existing jobs and historical timestamps.
- \`app.py\`: strict request validation and action routes; never expose block-device writes.
- \`update_manager.py\`: ff-only dashboard updates and one-revision rollback, blocked while builds run.
- WIFICAM image assembler, MMC offsets and recovery/SSH must not be casually changed.
- Private \`local/wifi.env\`, \`out/private-sd/\` and credentials must never be published.

## Development workflow

Create a feature branch from \`main\`, edit and comment relevant sources, add regression tests, run Python unittest, compileall and shell syntax, open a PR, require green GitHub Actions and merge into \`main\`. The System tab will signal a new update; install by explicit click when no build is active. Do not force-push main or manually reset a running server checkout.

## Release gates are separate

**Dashboard release:** versioned YadroKreator Git SHA, test suite and deployment/rollback; no camera flashing.

**Camera firmware release:** pinned WIFICAM and Thingino SHA → Buildroot and full-disk SD image (\`PUBLISH=0\`) → read-only image preflight (checksum/MBR/MSPL/FAT/uImage/ext4) → explicit whole-SD write at **LBA0** with readback SHA → physical camera boot, SSH, web UI :8090, CGI, RTSP, Wi-Fi, PTZ and recovery → publish sanitized RU/EN release notes and a clean, non-private image if all tests pass. Do not claim the newly assembled image is hardware-proven before this last gate.

Use the [architecture tree](ARCHITECTURE_EN.md), [preflight guide](PREFLIGHT_EN.md) and [Git deployment](GIT_DEPLOY_EN.md). Preview SVGs illustrate UI and pipeline, not live server screenshots.
