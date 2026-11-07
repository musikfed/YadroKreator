"""Regression tests for the T23N SD preflight. All I/O is on a temp file.

A generated 19-MiB sparse test image is intentionally NOT camera firmware; it
only exercises binary parsing and corruption rejection without a real device.
"""
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from artifact_checks import artifact_path, validate_t23n, validate_helper_t23n, layout_svg, save_report, saved_report

SECTOR = 512
ROOT_LBA = 34816


def make_fixture(image: Path) -> None:
    image.parent.mkdir(parents=True, exist_ok=True)
    root_sectors = 4096
    with image.open("wb") as f:
        f.truncate((ROOT_LBA + root_sectors) * SECTOR)
    with image.open("r+b") as f:
        mbr = bytearray(512)
        mbr[510:512] = b"\x55\xaa"
        mbr[446 + 4] = 0x0e
        mbr[462 + 4] = 0x83
        struct.pack_into("<II", mbr, 446 + 8, 2048, 32768)
        struct.pack_into("<II", mbr, 462 + 8, ROOT_LBA, root_sectors)
        f.write(mbr)
        f.seek(34 * SECTOR)
        f.write(bytes.fromhex("4c50534d"))
        boot = bytearray(512)
        struct.pack_into("<H", boot, 11, 512) # sector bytes
        boot[13] = 1                        # sectors per cluster
        struct.pack_into("<H", boot, 14, 1) # reserved
        boot[16] = 2                        # number FATs
        struct.pack_into("<H", boot, 17, 512) # root entries
        struct.pack_into("<H", boot, 22, 32) # sectors per FAT
        boot[510:512] = b"\x55\xaa"
        f.seek(2048 * SECTOR)
        f.write(boot)
        # FAT16 root begins at 1 + 2*32 = 65 sectors in partition.
        root = bytearray(32)
        root[:11] = b"UIMAGE     "
        root[11] = 0x20
        struct.pack_into("<H", root, 26, 2)
        struct.pack_into("<I", root, 28, 128)
        f.seek((2048 + 65) * SECTOR)
        f.write(root)
        # data cluster=2 begins at 1 + 2*32 + 32 = 97
        header = bytearray(64)
        header[:4] = bytes.fromhex("27051956")
        struct.pack_into(">I", header, 12, 64)
        header[32:44] = b"T23N Test OS"
        f.seek((2048 + 97) * SECTOR)
        f.write(header)
        f.seek(ROOT_LBA * SECTOR + 1024 + 56)
        f.write(b"\x53\xef")
    checksum = hashlib.sha256(image.read_bytes()).hexdigest()
    image.with_name(image.name + ".sha256").write_text(checksum+"  "+image.name+"\n")


class T23NPreflight(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job = dict(id="a"*32, profile="t23n_sd", status="success")
        self.image = self.root / "build/projects/wificam_T23N/jobs" / self.job["id"] / (
            "wificam_T23N/out/private-sd/thingino-t23-sd.bin")
        make_fixture(self.image)

    def tearDown(self):
        self.temp.cleanup()

    def test_pass_and_live_svg(self):
        image = artifact_path(self.job, self.root)
        self.assertEqual(image, self.image)
        result = validate_t23n(image)
        self.assertTrue(result["verified"])
        self.assertEqual(result["bootloader"]["start_lba"], 34)
        self.assertEqual(result["partitions"][1]["start_lba"], 34816)
        self.assertEqual(result["kernel_bytes"], 128)
        svg = layout_svg(result)
        self.assertIn("T23N SD image", svg)
        self.assertIn("BOOT", svg)
        self.assertIn("LBA 34816", svg)
        self.assertIn("NOT SD readback", result["scope"])
        save_report(self.job["id"], result, image, self.root / "factory-state")
        loaded = saved_report(self.job, self.root, self.root / "factory-state")
        self.assertTrue(loaded["verified"])


    def test_helper_candidate_requires_web_role_controls_inside_rootfs(self):
        # A valid MBR/kernel/marker alone is insufficient for a usable Helper UI.
        tokens = (b"PEGINELAB_HELPER_FIRMWARE_V1", b"peginelab.camera-head.v1",
                  b"helper-capabilities", b'id="helperNav"',
                  b'id="helperRobotMode"', b'id="helperVoiceMode"')
        with self.image.open("r+b") as stream:
            stream.seek(ROOT_LBA * SECTOR + 4096)
            stream.write(b" ".join(tokens[:3]))
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.image.with_name(self.image.name + ".sha256").write_text(digest + "\n")
        with self.assertRaisesRegex(ValueError, "role UI"):
            validate_helper_t23n(self.image)
        with self.image.open("r+b") as stream:
            stream.seek(ROOT_LBA * SECTOR + 4096)
            stream.write(b" ".join(tokens))
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.image.with_name(self.image.name + ".sha256").write_text(digest + "\n")
        report = validate_helper_t23n(self.image)
        self.assertTrue(report["helper_role_ui_verified"])

    def test_git_tracked_baseline_never_accepted_as_new_job(self):
        baseline = self.image.parents[2] / "Thingino/thingino-t23-sd.bin"
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(b"historical 0.1_test baseline")
        self.image.unlink()
        with self.assertRaisesRegex(FileNotFoundError, "No SD image"):
            artifact_path(self.job, self.root)

    def test_tampering_invalidates_checksum(self):
        with self.image.open("r+b") as f:
            f.seek(34 * SECTOR)
            f.write(b"wrong")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            validate_t23n(self.image)

    def test_wrong_boot_offset_even_with_correct_sha_is_rejected(self):
        with self.image.open("r+b") as f:
            f.seek(34 * SECTOR)
            f.write(b"\0"*4)
        digest=hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.image.with_name(self.image.name + ".sha256").write_text(digest+"\n")
        with self.assertRaisesRegex(ValueError, "MSPL"):
            validate_t23n(self.image)

    def test_reject_non_success_and_no_generalized_profile(self):
        for job in (
            dict(self.job, status="failed"),
            dict(self.job, profile="arm64_kernel"),
        ):
            with self.assertRaises(ValueError):
                artifact_path(job, self.root)

    def test_validation_becomes_stale_if_file_changes(self):
        result=validate_t23n(self.image)
        save_report(self.job["id"], result, self.image, self.root / "factory-state")
        with self.image.open("ab") as f:
            f.write(b"changed")
        state=saved_report(self.job, self.root, self.root / "factory-state")
        self.assertFalse(state["verified"])


if __name__ == "__main__":
    unittest.main()
