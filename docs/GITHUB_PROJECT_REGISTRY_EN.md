# Project-local images and opt-in GitHub source registration

Firmware images have moved under **WIFICAM T23N → Images & SD**, beside that project's builds. The global Images sidebar item is gone. The known-bootable `0.1_test` baseline stays untouched; it is not a new job artifact.

**Existing T23N build:** In System → GitHub sources, register an existing branch of the fixed `musikfed/wificam_T23N` repository. The server performs a read-only `git ls-remote` and adds it to the local allowlist. The normal T23N build runner pins an immutable Git SHA per job. The opt-in WifCam Helper preset is restricted to `mymarrchWFcam`.

**New repository:** Register a short ID, title, `musikfed/repo` and existing branch. A new project lane appears automatically in both the sidebar and overview, with Source/GitHub (read-only SHA refresh), Builds, Images, Logs, and Settings. Its build mode is `pending_adapter` by design: arbitrary upstream Git scripts may NOT be executed. Enabling an actual Linux kernel build requires an audited build adapter/toolchain, an isolated worker and image validator committed to the YadroKreator codebase.

Metadata is stored privately at `factory-state/registered-projects.json`; existing SQLite job history and private images are not migrated, deleted or reassigned.

Update via SSH on the Huananzhi server, never by reloading a stopped dashboard:

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash deploy.sh --check
bash deploy.sh --apply
bash scripts/rebuild-from-git.sh --check
bash scripts/rebuild-from-git.sh --apply --clean-cache
```

No generic Docker containers are part of the native Waitress/systemd factory. Never run global Docker prune or delete unrelated project images, LLMs, caches or SQLite. The update doesn't flash the T23N microSD or start a kernel build. Access the private panel through trusted LAN/VPN, not WAN.
