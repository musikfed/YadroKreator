# YadroKreator ↔ WifCam Helper — safe build contract

The four sibling repos under `/1tbdisk/PegineLab/projects/` stay distinct: YadroKreator builds from pinned WIFICAM Git source; WifCam Helper measures camera capabilities; Hombo3 consumes RTSP/audio for CV/STT/LLM/TTS. Pinned Thingino is at `/1tbdisk/PegineLab/build/thingino-firmware`.

Run Helper on CORE Ubuntu 24.04 Python 3.12 with `uv run --no-project python3 -m wifcam_helper web`; it listens on `127.0.0.1:8765` only. For remote access use an SSH tunnel. ffmpeg/ffprobe and SSH test the real camera and never modify firmware or restart Raptor.

In the YadroKreator Builds tab select the desired WIFICAM branch and explicitly tick **Use approved WifCam Helper preset**. The only accepted sibling file is `projects/wifcam_helper/profiles/t23n_lean.json` with exact schema, exact Galayou T23N camera, `mymarrchWFcam` branch and `WIFICAM_WEBRTC=0|1`. The factory pins a private `build/jobs/<id>/helper-preset.json` snapshot (0600); the worker independently revalidates it. The option is off by default. Absolutely no shell commands, arbitrary kernel overrides or PUBLISH=1 cross the boundary.

**Kernel scope:** WIFICAM's pinned Thingino profile still builds the Linux kernel, BusyBox, drivers and ext4 SD image. Helper cannot autonomously rewrite a Linux .config. Any future sensor/kernel changes require separate review and physical tests. RTSP connection/throughput measurements do not prove glass-to-glass latency or camera acoustics.

Keep Wi-Fi, SSH, GPU service credentials and TLS private keys out of Git. The existing `~/crt-cert/` files are left untouched. Optional YOLO runs only with a locally supplied trusted model and explicit consent; no cloud service, GPU power action, Linux service changes or SD writing happen automatically.

## Keep new candidates separate from the 0.1_test recovery baseline

With `PUBLISH=0`, a successful YadroKreator firmware job must produce a **new** `out/candidate-sd/thingino-t23-sd.bin` or `out/private-sd/thingino-t23-sd.bin` (when private Wi-Fi is provisioned), plus a neighboring `.sha256` file. Without those files, the job is not a successful firmware output. The Git-tracked `Thingino/thingino-t23-sd.bin` baseline is never treated as a newly built or downloadable job artifact.

Before writing a physical microSD, run the factory image preflight (SHA256, MBR, MSPL LBA34, FAT16 BOOT/uImage LBA2048, ext4 ROOTFS LBA34816). After boot, physically test SD boot, Wi-Fi/SSH, Web UI :8090 and CGI, RTSP/video, microphone, speaker, PTZ, and night mode. WifCam Helper performs CORE-side A/V tests only, never firmware flashing. Rufus/Etcher must write the **whole raw disk image to the camera microSD from LBA0**, not create a PC installer USB. Keep the working baseline card available for recovery.
