# Offline T23N SD image verification before flashing

In **Builds**, select a *completed successful* WIFICAM \`t23n_sd\` job, then click **Check SD image**. The button is read-only and cannot write any block device, download a private image, or test the physical camera.

Checks: image SHA256 matches its sidecar; DOS/MBR \`55aa\`, 512-byte sectors; T23N MSPL signature at **LBA34**; BOOT p1 starts **LBA2048**, 16 MiB FAT16 LBA, contains \`/uImage\` with U-Boot magic; ext4 ROOTFS p2 starts **LBA34816**, is within image bounds. Only an image from the completed job's isolated worktree is accepted. A failed, corrupt, missing, symlinked or stale image is rejected.

The derived \`/api/jobs/<id>/layout.svg\` is a live schematic drawn from verified file offsets. The persistent check record contains only SHA256, size, mtime and structural metadata; **no private Wi-Fi keys**. A green check means only image structure and file checksum succeeded, NOT physical SD readback, camera boot, Wi-Fi, RTSP or PTZ. Validate each stage independently; do not label a release as hardware-tested before testing the actual camera.

The profile-specific validator is \`artifact_checks.py\`; other boards need their own validators, not T23N's fixed LBA34 layout.

Timing: start/finish are persisted UTC timestamps. During an active build, an ETA and a capped estimated progress bar come from the median of at most five previous successful same-profile, same-branch build durations. Before history exists, progress is indeterminate. These are time estimates, **not measured compiler percentages**.

For flashing, use the WIFICAM repository SD writer only after checking the target with \`lsblk\`. Complete SD images are written at **LBA0**; bootloader alignment at LBA34 is already inside the image. Never add \`dd seek=34\`. Physical camera checklist: SD boot, SSH, :8090 web UI, CGI API, RTSP, PTZ, Wi-Fi and recovery.

[Architecture](ARCHITECTURE_EN.md) · [Editing/release guide](MODIFY_RELEASE_EN.md) · [UI preview](previews/preflight-dashboard.svg).
