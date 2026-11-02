"""Reject accidental check-in of private SD disk images.

CI can test our Python image format/layout code without storing a finished
camera image or Wi-Fi secrets in the YadroKreator Git repository.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = (".img", ".bin", ".img.xz", ".img.gz", ".iso", ".qcow2", ".vmdk")
FORBIDDEN_DIRS = {"private-sd", "candidate-sd", "factory-state", "build", "output"}


class PublicRepositorySizeAndSecrecy(unittest.TestCase):
    def test_no_flashable_firmware_artifacts_are_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        )
        files = [x.decode("utf-8", "replace") for x in result.stdout.split(b"\x00") if x]
        leaked = []
        for file in files:
            path = Path(file)
            if file.lower().endswith(FORBIDDEN_SUFFIXES) or (
                any(part in FORBIDDEN_DIRS for part in path.parts)
                and path.suffix not in (".md", ".svg", ".txt")
            ):
                leaked.append(file)
        self.assertEqual(leaked, [], "Private/large firmware images must stay on Huananzhi, not in Git")


if __name__ == "__main__":
    unittest.main()
