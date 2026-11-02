# Download and write a verified T23N whole-disk SD image

The YadroKreator **Artifacts** panel offers a **Download .img** button for successful jobs only after the **Check SD image** preflight passes (SHA256/MBR/MSPL at LBA34/FAT16 uImage at LBA2048/ext4 at LBA34816). This does NOT verify camera hardware.

Since personal Wi-Fi credentials may be embedded and the dashboard has no login, downloads require an **SSH-issued, one-use, 10-minute token**. On Huananzhi:

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
python3 download_access.py issue FULL_JOB_ID
```

Copy the complete job ID from its artifact card. Paste the token into the browser Download button. The downloaded `.img` contains the **exact same bytes** as the server-side `.bin`; no layout changes are applied. The token is not placed in a URL or repo. **Warning:** plain HTTP on an untrusted LAN exposes token/contents to sniffing. Restrict the service to trusted LAN/VPN with secure transport, or use SSH/SCP instead.

**Windows:** choose the `.img` in Rufus or balenaEtcher, choose the correct SD card in a reader (all existing data will be destroyed), write the complete raw disk image, wait for verification, and safely eject. Never format ext4 when Windows prompts.

**Linux:** run `lsblk -o NAME,PATH,SIZE,MODEL,TRAN,RM,MOUNTPOINTS` to verify the USB removable card first. Then run the WIFICAM job's `scripts/write_thingino_wificam_sd.sh` with the exact whole-disk device path and verified image path; the writer checks the reader, confirmation string and full SHA256 readback. **The image starts at LBA0, not LBA34; the MSPL is already at LBA34 inside the image.** Never use an extra `seek=34`.

Finally, power down the camera, insert SD, then test real SD boot, SSH, Wi-Fi, web :8090, CGI, RTSP, PTZ and recovery. Only physical hardware testing can establish a release as verified.
