# Isolated YadroKreator project lanes: WIFICAM / Irila / Helper

The updated dashboard has separate **WIFICAM T23N**, **Irila Baikal**, **WifCam Helper**, **WIFICAM images**, and **System** tabs.

| Lane | Pinned source | Build action |
|---|---|---|
| T23N SD | `musikfed/wificam_T23N` (`main` or `mymarrchWFcam`) | Real Ingenic MIPS Thingino SD candidate, isolated job checkout |
| Irila Baikal | `musikfed/Irila_baikal_v1.0` `main` | Safe immutable-source audit only. Real x86-64 Secure Boot IMG is built by [Irila's GitHub Actions workflow](https://github.com/musikfed/Irila_baikal_v1.0/actions/workflows/build-installed-full-secureboot-img.yml). |
| WifCam Helper | `musikfed/wifcam_helper` | Camera diagnostic suite; optional validated preset (only `WIFICAM_WEBRTC=0|1`) |
| YadroKreator | `musikfed/YadroKreator` | Dashboard, SQLite jobs, separate logs, systemd user workers |

Canonical sibling source directories are `/1tbdisk/PegineLab/projects/{YadroKreator,wificam_T23N,wifcam_helper,Irila_baikal_v1.0}`. The name `wificam_T23N` includes a trailing N; do not conflate it with `wificam_T23`.

Each job pins its Git SHA and has a unique `build/jobs/<uuid>/<repo>/` checkout. The repositories have distinct bare Git caches. Per-job logs live under `factory-state/logs/<uuid>.log`. T23N SD images alone can be downloaded through the existing image preflight; Irila's JSON audit is **never** returned as a firmware image.

**Global concurrency policy: one YadroKreator job at a time.** The database transaction rejects jobs while any queued/running/stopping job exists, and the worker holds an exclusive file lock at `build/locks/factory-build.lock`. This protects factory jobs only; external manual `make` processes or separate GitHub Actions are not locked. A full project stop enumerates both `peginelab-t23n-*` and `peginelab-irila-*` user systemd units.

**Important Irila safety boundary:** its officially supported IMG packaging uses privileged loop devices, mkfs, mount and signed Ubuntu x86-64 kernels. An unattended local root/IMG builder is intentionally *not* exposed through the LAN dashboard until a separate confined and explicitly verified privileged worker exists. The Irila button in the dashboard runs only read-only, Git-pinned source audit. It does not build a kernel/IMG.

Updating YadroKreator from GitHub updates dashboard code, not the sibling repositories, and starts no builds automatically. The Helper preset requires its local file to be present.
