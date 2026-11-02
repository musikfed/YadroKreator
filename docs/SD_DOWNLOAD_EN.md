# Download and write a verified T23N whole-disk SD image

The YadroKreator **Artifacts** panel offers a **Download .img** button as soon as a T23N SD build succeeds. No kernel rebuild is required. The download endpoint automatically runs image preflight on the existing bytes before sending them (SHA256/MBR/MSPL at LBA34/FAT16 uImage at LBA2048/ext4 at LBA34816). This does NOT verify camera hardware.

**One-click export:** on **Artifacts**, click **Download .img** for a successful T23N job. There is no SSH ticket, terminal command or manual job ID. The server validates the existing complete image (SHA256 + partitions) and transfers its unchanged bytes; **no kernel rebuild or SD write occurs**.

**Security trade-off:** the dashboard does not authenticate users and firmware may embed personal Wi-Fi keys. The HTTP endpoint only allows clients from `192.168.0.0/24` or loopback by default. **Every device on the trusted subnet could download the image.** Keep port 62404 off the public Internet and exclude untrusted Wi-Fi guests. For other VPN subnets the server admin can configure `PEGINELAB_EXPORT_TRUSTED_NETWORKS` (comma-separated CIDR networks; `0.0.0.0/0` is forbidden). This is network segmentation, NOT user authentication or encryption; use secure VPN/HTTPS or SCP for remote export.

**GitHub:** retain source, offline image layout tests, checksums/manifests without secrets; never commit the private `.bin`/`.img` files to the repository. A CI regression test rejects accidentally tracked firmware images.

**Windows:** choose the `.img` in Rufus or balenaEtcher, choose the correct SD card in a reader (all existing data will be destroyed), write the complete raw disk image, wait for verification, and safely eject. Never format ext4 when Windows prompts.

**Linux:** run `lsblk -o NAME,PATH,SIZE,MODEL,TRAN,RM,MOUNTPOINTS` to verify the USB removable card first. Then run the WIFICAM job's `scripts/write_thingino_wificam_sd.sh` with the exact whole-disk device path and verified image path; the writer checks the reader, confirmation string and full SHA256 readback. **The image starts at LBA0, not LBA34; the MSPL is already at LBA34 inside the image.** Never use an extra `seek=34`.

Finally, power down the camera, insert SD, then test real SD boot, SSH, Wi-Fi, web :8090, CGI, RTSP, PTZ and recovery. Only physical hardware testing can establish a release as verified.
