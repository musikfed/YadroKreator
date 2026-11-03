# YadroKreator ↔ WifCam Helper — safe build contract

The four sibling repos under `/1tbdisk/PegineLab/projects/` stay distinct: YadroKreator builds from pinned WIFICAM Git source; WifCam Helper measures camera capabilities; Hombo3 consumes RTSP/audio for CV/STT/LLM/TTS. Pinned Thingino is at `/1tbdisk/PegineLab/build/thingino-firmware`.

Run Helper on CORE Ubuntu 24.04 Python 3.12 with `uv run --no-project python3 -m wifcam_helper web`; it listens on `127.0.0.1:8765` only. For remote access use an SSH tunnel. ffmpeg/ffprobe and SSH test the real camera and never modify firmware or restart Raptor.

In the YadroKreator Builds tab select the desired WIFICAM branch and explicitly tick **Use approved WifCam Helper preset**. The only accepted sibling file is `projects/wifcam_helper/profiles/t23n_lean.json` with exact schema, exact Galayou T23N camera, `mymarrchWFcam` branch and `WIFICAM_WEBRTC=0|1`. The factory pins a private `build/jobs/<id>/helper-preset.json` snapshot (0600); the worker independently revalidates it. The option is off by default. Absolutely no shell commands, arbitrary kernel overrides or PUBLISH=1 cross the boundary.

**Kernel scope:** WIFICAM's pinned Thingino profile still builds the Linux kernel, BusyBox, drivers and ext4 SD image. Helper cannot autonomously rewrite a Linux .config. Any future sensor/kernel changes require separate review and physical tests. RTSP connection/throughput measurements do not prove glass-to-glass latency or camera acoustics.

Keep Wi-Fi, SSH, GPU service credentials and TLS private keys out of Git. The existing `~/crt-cert/` files are left untouched. Optional YOLO runs only with a locally supplied trusted model and explicit consent; no cloud service, GPU power action, Linux service changes or SD writing happen automatically.
