# PegineLab CORE: safe GitHub sync, branch audit and old storage cleanup

Use as the normal Ubuntu 24.04 service user on Huananzhi X79 `192.168.0.100` — **never sudo/root**.

For a first install:
```bash
mkdir -p /1tbdisk/PegineLab/projects
cd /1tbdisk/PegineLab/projects
git clone https://github.com/musikfed/YadroKreator.git
cd YadroKreator
bash bootstrap.sh
```
Bootstrap checks out the three sibling repositories into separate `projects/` directories, prepares the pinned Thingino revision and installs the factory. Existing dirty, unexpected or symlinked worktrees are **never** overwritten.

For an already installed factory, update YadroKreator through the System tab or `bash deploy.sh --apply` first if the sync script has not yet been installed. Then:
```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash scripts/sync_core_projects.sh                          # dry-run
bash scripts/sync_core_projects.sh --apply                  # sync 3 siblings
bash scripts/sync_core_projects.sh --apply --with-factory   # optionally update factory with its approved updater
```
All existing checkouts retain their checked-out branch. Only a clean, known Git `origin` and a **fast-forward** update are accepted. No reset, clean, force update, SD flashing, camera restart or automatic kernel build occurs.

WIFICAM factory jobs already fetch and SHA-pin `main` or `mymarrchWFcam` from GitHub directly into a per-job worktree; a local source `git pull` is not required to run a WIFICAM job. The local Helper JSON file *does* require a synced checkout. Irila source audits likewise fetch the source SHA separately; real privileged Secure Boot IMG creation is still a separate GitHub Actions workflow.

## Protected remote branches

```bash
bash scripts/prune_merged_branches.sh --project YadroKreator
bash scripts/prune_merged_branches.sh --project wificam_T23N
bash scripts/prune_merged_branches.sh --project YadroKreator --branch feature/dashboard-updates-rollback
bash scripts/prune_merged_branches.sh --project YadroKreator --branch feature/dashboard-updates-rollback --apply --confirm DELETE-MERGED-REMOTE-BRANCHES
```
The branch script deletes *only explicitly named* remote branches entirely reachable from `main`, and only using an exact SHA lease. `main`, WIFICAM `mymarrchWFcam` and the hardware reference `release/0.1_test` are always protected. Diverged or unmerged branches, local branches, unknown Git remotes and active build jobs block deletion. A GitHub account/token configured on the server is needed for remote deletion.

## Clean legacy-only build storage

```bash
bash scripts/cleanup_old_results.sh
bash scripts/cleanup_old_results.sh --include-orphans --prune-old-git-cache --prune-old-shared-cache
bash scripts/cleanup_old_results.sh --include-orphans --prune-old-git-cache --prune-old-shared-cache --apply --confirm DELETE-LEGACY-JOBS
```
It lists and optionally removes only legacy `build/jobs/<uuid>`, old shared logs/validation, old `build/git-cache`, old shared `build/cache` and `build/tmp`, plus old completed SQLite job rows. It never deletes source `projects/`, new per-project `build/projects/`, the sqlite database, pinned Thingino, known-good T23 SD reference, TLS keys, unrelated services or active jobs. It refuses symlinks and ongoing factory updates. GitHub does **not** necessarily contain private locally built IMG/BIN files; review every dry-run entry before approval.

[Project isolation](MULTI_PROJECT_BUILDS_EN.md).
