"""WifCam Helper is a separate, pinned firmware, never a diagnostic-only alias."""
from __future__ import annotations
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from helper_firmware import APPROVED, APPROVED_UI, MARKER, stage_helper_overlay, SHA
from helper_audio import SAMPLE_RATE, inspect_voice
from project_profiles import job_root, project_build_root
from git_sources import workspace_for

ID="e"*32
HASH="a"*40

class HelperFirmwareTests(unittest.TestCase):
    def make_trees(self,base: Path):
        job=job_root(ID,"t23n_helper_sd",root=base)
        helper=job/"wifcam_helper"
        camera=workspace_for(ID,base,profile="t23n_helper_sd")
        for relative in APPROVED:
            file=helper/"firmware/overlay"/relative
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(("PEGINELAB_HELPER_FIRMWARE_V1" if "release" in relative
                 else "peginelab.camera-head.v1")+"\n")
        (camera/"rootfs").mkdir(parents=True)
        for relative in APPROVED_UI:
            file = helper/"firmware/ui"/relative
            file.parent.mkdir(parents=True,exist_ok=True)
            content = (
                "<html>PegineLab WIFICAM T23N</html>" if relative == "index.html"
                else "fetch('/cgi-bin/helper-capabilities')" if relative == "app.js"
                else "x" if relative == "styles.css" else "<svg></svg>"
            )
            file.write_text(content)
            base_file = camera/"web"/relative
            base_file.parent.mkdir(parents=True,exist_ok=True)
            base_file.write_text("base")
        sound = helper/"firmware/audio/boot-voice.wav"
        sound.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(sound),"wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(b"\\0\\0" * SAMPLE_RATE)
        return job,helper,camera

    def test_separate_rootfs_and_dual_source_pins(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job,helper,camera=self.make_trees(root)
            self.assertNotEqual(project_build_root("t23n_helper_sd",root=root),
                                project_build_root("t23n_sd",root=root))
            path=stage_helper_overlay(helper,camera,ID,HASH,"b"*40,root=root)
            pins=json.loads(path.read_text())
            self.assertEqual(pins["helper_sha"],HASH)
            self.assertEqual(pins["base_sha"],"b"*40)
            for relative,mode in APPROVED.items():
                target=camera/"rootfs"/relative
                self.assertTrue(target.is_file())
                self.assertEqual(target.stat().st_mode & 0o777,mode)
            self.assertIn(MARKER,(camera/"rootfs/etc/wifcam-helper-release").read_bytes())
            for relative in APPROVED_UI:
                self.assertEqual((camera/"web"/relative).read_bytes(),
                                 (helper/"firmware/ui"/relative).read_bytes())
            self.assertEqual((camera/"web/assets/boot-voice.s16le").stat().st_size,SAMPLE_RATE*2)
            self.assertGreater((camera/"web/assets/boot-voice.wav").stat().st_size,SAMPLE_RATE*2)
            self.assertIn("audio/boot-voice.s16le",pins["media_sha256"])
            with self.assertRaises(RuntimeError):
                stage_helper_overlay(helper,camera,ID,HASH,"b"*40,root=root)

    def test_rejects_extra_code_or_overlay_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job,helper,camera=self.make_trees(root)
            extra=helper/"firmware/overlay/etc/random-shell"
            extra.write_text("unexpected")
            with self.assertRaises(ValueError):
                stage_helper_overlay(helper,camera,ID,HASH,"b"*40,root=root)
            extra.unlink()
            file=helper/"firmware/overlay/usr/bin/wifcam-helper-probe"
            file.unlink()
            victim=root/"other-project"
            victim.write_text("secret")
            file.symlink_to(victim)
            with self.assertRaises(ValueError):
                stage_helper_overlay(helper,camera,ID,HASH,"b"*40,root=root)
            self.assertEqual(victim.read_text(),"secret")

    def test_rejects_ui_symlink_and_invalid_voice_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job,helper,camera=self.make_trees(root)
            ui=helper/"firmware/ui/app.js"
            ui.unlink()
            ui.symlink_to(root/"secret")
            with self.assertRaises(ValueError):
                stage_helper_overlay(helper,camera,ID,HASH,"b"*40,root=root)
            self.assertFalse((camera/"rootfs/etc/wifcam-helper-release").exists())
            ui.unlink()
            ui.write_text("fetch('/cgi-bin/helper-capabilities')")
            (helper/"firmware/audio/boot-voice.wav").write_text('{"bad":"audio"}')
            with self.assertRaises(ValueError):
                stage_helper_overlay(helper,camera,ID,HASH,"b"*40,root=root)
            self.assertFalse((camera/"rootfs/etc/wifcam-helper-release").exists())

    def test_spoken_voice_pcm_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job,helper,camera=self.make_trees(root)
            first=stage_helper_overlay(helper,camera,ID,HASH,"b"*40,root=root)
            sha1=json.loads(first.read_text())["media_sha256"]["audio/boot-voice.s16le"]
            self.assertEqual(len(sha1),64)
            self.assertEqual(inspect_voice(helper/"firmware/audio/boot-voice.wav")[0],SAMPLE_RATE)

    def test_invalid_sha_never_writes_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job,helper,camera=self.make_trees(root)
            with self.assertRaises(ValueError):
                stage_helper_overlay(helper,camera,ID,"main","b"*40,root=root)
            self.assertFalse((camera/"rootfs/etc/wifcam-helper-release").exists())

    def test_manifest_is_real_camera_firmware_not_full_host_python(self):
        self.assertTrue(SHA.fullmatch(HASH))
        self.assertEqual(set(APPROVED),{
            "etc/wifcam-helper-release",
            "etc/init.d/S92wifcam-helper",
            "usr/bin/wifcam-helper-probe",
            "usr/bin/wifcam-helper-mode",
            "usr/share/wificam-web/cgi-bin/helper-capabilities",
        })

if __name__=="__main__":
    unittest.main()
