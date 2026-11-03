# YadroKreator · fully isolated per-project builds

PegineLab CORE is the shared **scheduler**, not a shared production directory. Every project has its own Git cache, temporary directory, build cache, immutable SHA-pinned per-job checkout, generated artifacts, logs and validation reports. SQLite and the global **one-active-worker** lock are the only shared coordination facilities. These paths are independent from the source repositories under `projects/`.

## Project-specific lanes

| Dashboard lane | Project | Actual supported action |
|---|---|---|
| **WIFICAM T23N** | `musikfed/wificam_T23N` | Build full Ingenic MIPS Thingino SD firmware from a pinned source commit |
| **Irila Baikal** | `musikfed/Irila_baikal_v1.0` | SHA-pinned source audit, separate JSON download; real x86-64 Secure Boot IMG is in [Irila GitHub Actions](https://github.com/musikfed/Irila_baikal_v1.0/actions/workflows/build-installed-full-secureboot-img.yml) |
| **WifCam Helper** | `musikfed/wifcam_helper` | Separate read-only camera test suite; optionally supply a strict `WIFICAM_WEBRTC=0|1` build preset |
| **System** | `musikfed/YadroKreator` | Update, restart and stop dashboard/owned jobs only |

```text
/1tbdisk/PegineLab/
  projects/{YadroKreator,wificam_T23N,Irila_baikal_v1.0,wifcam_helper}/
  build/
    projects/
      wificam_T23N/{git-cache,tmp,cache,jobs/<id>/wificam_T23N/out/}
      Irila_baikal_v1.0/{git-cache,tmp,cache,jobs/<id>/Irila_baikal_v1.0/}
    locks/factory-build.lock
    thingino-firmware/                  # pinned WIFICAM-specific upstream
  factory-state/
    factory.sqlite3
    projects/
      wificam_T23N/{logs,validation}/
      Irila_baikal_v1.0/logs/
    update-logs/
```

**Keep the trailing N:** `wificam_T23N` is not the same folder as `wificam_T23`.

The dashboard visually separates the lanes by tabs, distinct color accents, path indicators, own history/logs, and project-specific downloads. WIFICAM SD image preflight can never validate or download the Irila source audit as a camera image.

Global concurrency is one active YadroKreator job. A SQLite transaction rejects a second queued/running/stopping job, and an independent worker `flock` prevents duplicate systemd launches. This lock does not govern externally run make processes or unrelated GitHub Actions.

## Explicitly delete obsolete legacy results

Earlier factory versions wrote under `build/jobs/<id>` and `factory-state/logs/<id>.log`. These old job results are not implicitly reused or moved. If they are no longer wanted, run the guarded cleanup on the Ubuntu machine, **only after reviewing the dry-run**:

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
python3 scripts/cleanup_legacy_builds.py
python3 scripts/cleanup_legacy_builds.py --apply --confirm DELETE-LEGACY-JOBS
# Optional; does not touch new project-specific caches:
python3 scripts/cleanup_legacy_builds.py --prune-old-git-cache
python3 scripts/cleanup_legacy_builds.py --apply --confirm DELETE-LEGACY-JOBS --prune-old-git-cache
```

It refuses active jobs, a held build lock, symlinked legacy paths or an unexpected database state. It deletes only old completed UUID workspaces, old logs and validation files and matching legacy SQLite rows; the old bare Git caches are an additional opt-in. The source trees under `projects/`, new `build/projects/`, Thingino upstream, `factory-state/factory.sqlite3`, baseline `Thingino/thingino-t23-sd.bin`, HTTPS keys and unrelated services are never targeted.

**GitHub stores committed sources, not necessarily built .img/.bin output or private logs.** A locally generated artifact can be the only copy. Git update does not run cleanup automatically.

Irila's privileged loop/mkfs packaging is intentionally **not** invoked from the dashboard until a separate bounded privileged worker has been designed and validated. The current Irila button is a source audit, not a kernel/IMG build. Physical camera/Acer tests are not covered by GitHub CI.
