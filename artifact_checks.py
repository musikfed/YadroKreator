"""Read-only, profile-specific checks of a COMPLETE T23N SD disk image.

This module never opens block devices, runs dd, formats partitions or boots
a camera. A green result means only that the on-disk image passed these
structural and checksum checks, NOT that physical SD boot / Wi-Fi / PTZ works.

To support another board, add a separate verified profile validator. Do NOT
reuse LBA34/partitions as universal offsets.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import struct
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from core import DATA, ROOT
from git_sources import workspace_for

SECTOR = 512
IMAGE_NAME = "thingino-t23-sd.bin"
SHA = re.compile(r"^[0-9a-f]{64}$")
JOB_ID = re.compile(r"^[0-9a-f]{32}$")

# T23N board-specific layout, from WIFICAM's SD assembler.
MSPL_LBA = 34
BOOT_LBA = 2048
BOOT_SECTORS = 32768
ROOT_LBA = 34816
MSPL_MAGIC = bytes.fromhex("4c50534d")  # od -tx4 => 4d53504c
UIMAGE_MAGIC = bytes.fromhex("27051956") # legacy U-Boot uImage header, big endian


def artifact_path(job: dict, root: Path = ROOT) -> Path:
    """Select only a per-job image; never use a path supplied by a browser."""
    if job.get("profile") != "t23n_sd" or job.get("status") != "success":
        raise ValueError("Only completed T23N SD builds can be checked")
    job_id = job.get("id", "")
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValueError("Invalid build ID")
    work = workspace_for(job_id, root)
    for relative in (
        "out/private-sd/" + IMAGE_NAME,
        "out/candidate-sd/" + IMAGE_NAME,
        "Thingino/" + IMAGE_NAME,
    ):
        candidate = work / relative
        if candidate.is_symlink():
            raise ValueError("Symlinked artifacts are not accepted")
        if candidate.is_file():
            if candidate.resolve().is_relative_to(work.resolve()):
                return candidate
    raise FileNotFoundError("No SD image found for this completed build")


def _must(check: bool, message: str) -> None:
    if not check:
        raise ValueError(message)


def validate_t23n(path: Path) -> dict:
    """Check full-image SHA, DOS MBR, exact LBA geometry, FAT16/uImage, ext4.

    The checksum file must be next to the image. Verification is calculated
    from actual bytes (not only the declared checksum). No image modification.
    """
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing image or symlinked image")
    count = path.stat().st_size
    _must(count >= (ROOT_LBA + 1) * SECTOR + 2048, "Image is too small")
    _must(count % SECTOR == 0, "Image is not 512-byte aligned")
    sidecar = path.with_name(path.name + ".sha256")
    _must(sidecar.is_file() and not sidecar.is_symlink(), "SHA256 sidecar is missing")
    line = sidecar.read_text(encoding="utf-8").splitlines()[0].split()
    _must(len(line) >= 1 and bool(SHA.fullmatch(line[0].lower())),
          "Invalid SHA256 sidecar")
    declared = line[0].lower()
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    _must(hmac.compare_digest(declared, actual), "SHA256 does not match image bytes")

    with path.open("rb") as f:
        mbr = f.read(SECTOR)
        _must(mbr[510:512] == b"\x55\xaa", "MBR signature not 55AA")
        p1 = mbr[446:462]
        p2 = mbr[462:478]
        _must(p1[4] == 0x0E and p2[4] == 0x83,
              "Expected FAT16-LBA p1 and Linux p2")
        s1, n1 = struct.unpack_from("<II", p1, 8)
        s2, n2 = struct.unpack_from("<II", p2, 8)
        _must((s1, n1, s2) == (BOOT_LBA, BOOT_SECTORS, ROOT_LBA),
              "T23N partition LBA or BOOT size mismatch")
        _must(n2 > 0 and (s2 + n2) * SECTOR <= count,
              "ROOTFS extends beyond the image")
        _must(s1 >= MSPL_LBA + 512 and s2 == s1 + n1,
              "Partition layout overlaps bootloader or has gaps")
        f.seek(MSPL_LBA * SECTOR)
        _must(f.read(4) == MSPL_MAGIC, "T23N MSPL magic missing at LBA34")

        boot = s1 * SECTOR
        f.seek(boot)
        bpb = f.read(SECTOR)
        _must(bpb[510:512] == b"\x55\xaa", "FAT boot-sector signature missing")
        bps = struct.unpack_from("<H", bpb, 11)[0]
        spc = bpb[13]
        reserved = struct.unpack_from("<H", bpb, 14)[0]
        fats = bpb[16]
        entries = struct.unpack_from("<H", bpb, 17)[0]
        spf = struct.unpack_from("<H", bpb, 22)[0]
        _must(bps == 512 and spc > 0 and spc <= 128 and
              spc & (spc - 1) == 0 and reserved > 0 and fats in (1, 2) and
              entries > 0 and spf > 0, "Invalid FAT16 BPB")
        root_sector = reserved + fats * spf
        root_bytes = entries * 32
        root_sectors = (root_bytes + bps - 1) // bps
        data_sector = root_sector + root_sectors
        _must(data_sector < n1, "FAT16 structure exceeds BOOT partition")
        f.seek(boot + root_sector * bps)
        directory = f.read(root_bytes)
        file_entry = None
        for pos in range(0, len(directory), 32):
            entry = directory[pos:pos + 32]
            if len(entry) < 32 or entry[0] == 0:
                break
            if entry[0] == 0xE5 or entry[11] == 0x0F:
                continue
            if entry[:11] == b"UIMAGE     ":
                file_entry = entry
                break
        _must(file_entry is not None, "BOOT FAT16 has no /uImage")
        cluster = struct.unpack_from("<H", file_entry, 26)[0]
        kernel_size = struct.unpack_from("<I", file_entry, 28)[0]
        _must(cluster >= 2 and kernel_size >= 64 and kernel_size < n1 * SECTOR,
              "Invalid uImage FAT directory entry")
        kernel_off = boot + (data_sector + (cluster - 2) * spc) * bps
        _must(kernel_off + 64 < boot + n1 * SECTOR,
              "uImage first cluster outside BOOT partition")
        f.seek(kernel_off)
        header = f.read(64)
        _must(header[:4] == UIMAGE_MAGIC, "uImage magic does not match")
        # uImage headers store the kernel payload size at offset 12.
        payload_size = struct.unpack_from(">I", header, 12)[0]
        _must(payload_size + 64 <= kernel_size,
              "uImage directory size is smaller than header payload")
        kernel_name = header[32:64].split(b"\0")[0].decode("ascii", "replace")
        kernel_name = "".join(ch for ch in kernel_name if 32 <= ord(ch) < 127)[:48]

        f.seek(s2 * SECTOR + 1024 + 56)
        _must(f.read(2) == b"\x53\xef", "ROOTFS ext4 superblock magic missing")

    return {
        "profile": "t23n_sd",
        "verified": True,
        "scope": "Image structure only — NOT SD readback / camera boot / Wi-Fi / PTZ",
        "sha256": actual,
        "bytes": count,
        "kernel_bytes": kernel_size,
        "kernel_name": kernel_name,
        "partitions": [
            {"name": "BOOT", "type": "FAT16", "start_lba": s1, "sectors": n1,
             "contains": "uImage"},
            {"name": "ROOTFS", "type": "ext4", "start_lba": s2, "sectors": n2,
             "contains": "WIFICAM / Linux"},
        ],
        "bootloader": {"start_lba": MSPL_LBA, "magic": "4d53504c"},
    }


def report_path(job_id: str, data: Path = DATA) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Invalid job ID")
    return data / "validation" / (job_id + ".json")


def save_report(job_id: str, result: dict, image: Path, data: Path = DATA) -> None:
    """Store metadata only, never a Wi-Fi secret or full image in the API."""
    path = report_path(job_id, data)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stat = image.stat()
    result = dict(result, image_bytes=stat.st_size, image_mtime_ns=stat.st_mtime_ns)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".validation-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def saved_report(job: dict, root: Path = ROOT, data: Path = DATA) -> dict | None:
    path = report_path(job["id"], data)
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        image = artifact_path(job, root)
        stat = image.stat()
        if (stat.st_size, stat.st_mtime_ns) != (
            result.get("image_bytes"), result.get("image_mtime_ns")
        ):
            return {"verified": False, "message": "Image changed: check again"}
        return result
    except (OSError, ValueError, json.JSONDecodeError):
        return {"verified": False, "message": "Validation stale / missing image"}


def layout_svg(report: dict) -> str:
    """Generate a diagram from actual checked offsets, never from user HTML."""
    _must(report.get("verified") is True, "Validate the image first")
    partitions = report["partitions"]
    boot, root = partitions
    sha = escape(report["sha256"][:16])
    name = escape(report.get("kernel_name", "uImage"))
    root_mib = root["sectors"] * SECTOR // 1048576
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 380" role="img" aria-label="T23N verified SD image map">
<rect width="940" height="380" rx="18" fill="#0d1422"/>
<text x="32" y="44" fill="#e5edff" font-family="sans-serif" font-size="23" font-weight="bold">T23N SD image · checked structure</text>
<text x="32" y="72" fill="#9cb1cc" font-family="monospace" font-size="13">SHA256 {sha}… · layout is schematic, not to scale</text>
<rect x="32" y="100" width="140" height="105" rx="9" fill="#22304a" stroke="#91aacb"/>
<rect x="180" y="100" width="147" height="105" rx="9" fill="#284b59" stroke="#59d2be"/>
<rect x="335" y="100" width="255" height="105" rx="9" fill="#133d49" stroke="#59d2be"/>
<rect x="598" y="100" width="310" height="105" rx="9" fill="#23315c" stroke="#81adff"/>
<g font-family="sans-serif" fill="#e5edff" font-size="15"><text x="45" y="132">MBR · LBA 0</text><text x="192" y="132">MSPL · LBA 34</text><text x="350" y="132">BOOT · FAT16</text><text x="613" y="132">ROOTFS · ext4</text></g>
<g font-family="monospace" fill="#9cb1cc" font-size="13"><text x="45" y="165">Partition table</text><text x="192" y="165">T23 boot magic</text><text x="350" y="165">LBA {boot["start_lba"]}</text><text x="350" y="187">uImage</text><text x="613" y="165">LBA {root["start_lba"]}</text><text x="613" y="187">{root_mib} MiB · WIFICAM</text></g>
<path d="M459 206 V248 M750 206 V248" stroke="#6d8cb6" fill="none" stroke-width="2"/>
<g font-family="sans-serif" fill="#e5edff" font-size="16"><text x="344" y="280">Linux kernel</text><text x="639" y="280">Linux root filesystem</text></g>
<g font-family="monospace" fill="#9cb1cc" font-size="13"><text x="344" y="305">{name}</text><text x="639" y="305">BusyBox · Web UI · CGI</text></g>
<text x="32" y="351" font-family="sans-serif" font-size="14" fill="#ffc980">Image-level verification only. Physical SD boot / Wi-Fi / PTZ need testing on camera.</text>
</svg>'''
