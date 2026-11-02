"""Launch/stop contract: dashboard service only; builds/host unaffected."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ProjectLifecycleTests(unittest.TestCase):
    def test_native_user_systemd_only(self):
        s = (ROOT / 'scripts/project-control.sh').read_text()
        self.assertIn('peginelab-factory.service', s)
        self.assertIn('systemctl --user start', s)
        self.assertIn('systemctl --user stop', s)
        self.assertIn('systemctl --user status', s)
        self.assertIn('id -u', s)
        for forbidden in ('sudo systemctl', 'docker stop', 'killall', 'pkill',
                          'systemctl --user stop peginelab-build', 'systemctl stop'):
            self.assertNotIn(forbidden, s)

    def test_windows_ssh_does_not_kill_processes(self):
        s = (ROOT / 'scripts/project-control.ps1').read_text()
        self.assertIn('ssh.exe', s)
        self.assertIn('systemctl --user', s)
        self.assertNotIn('Stop-Process', s)
        self.assertNotIn('taskkill', s)
        self.assertNotIn('sudo', s)

    def test_wrappers_present(self):
        for name in ('start.sh', 'stop.sh', 'start.ps1', 'stop.ps1'):
            self.assertTrue((ROOT / name).is_file(), name)

if __name__ == '__main__':
    unittest.main()
