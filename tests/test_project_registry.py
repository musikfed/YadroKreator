"""GitHub project registry safety, branch verification and isolated navigation.

No Internet, real build, Docker, filesystem pruning, or actual camera.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from project_registry import (
    add_branch, add_project, allowed_branches, load, validate_ref,
    validate_repo, validate_slug, git_ref_sha,
)


class ProjectRegistryTests(unittest.TestCase):
    def test_github_repo_and_branch_validation(self):
        self.assertEqual(validate_repo("https://github.com/musikfed/custom_kernel.git"),
                         "custom_kernel")
        self.assertEqual(validate_repo("musikfed/wificam_T23N"),"wificam_T23N")
        for bad in (
            "https://evil.example/musikfed/kernel",
            "https://github.com/other/kernel",
            "file:///etc/passwd",
            "musikfed/../../etc",
            "https://github.com/musikfed/kernel?token=abc",
            "musikfed/some/repo",
            "https://github.com@evil.example/musikfed/repo",
        ):
            with self.subTest(repo=bad), self.assertRaises(ValueError):
                validate_repo(bad)
        for bad in ("../etc","feature//test","foo.lock", "refs/heads/x", "@{hello}",
                    "--upload-pack=touch", "", None,"foo/.hidden","a..b"):
            with self.subTest(branch=bad), self.assertRaises(ValueError):
                validate_ref(bad)
        for bad in ("system","artifacts","../admin","foo_bar","A", "wificam"):
            with self.subTest(slug=bad),self.assertRaises(ValueError):
                validate_slug(bad)

    def test_only_confirmed_wificam_branch_becomes_buildable(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/"factory-state"
            self.assertEqual(allowed_branches(data),("mymarrchWFcam","main"))
            seen=[]
            def check(repo,branch):
                seen.append((repo,branch))
                return branch=="feature/kernel-3"
            with self.assertRaises(ValueError):
                add_branch("feature/unknown",data=data,verify=check)
            self.assertFalse((data/"registered-projects.json").exists())
            add_branch("feature/kernel-3",data=data,verify=check)
            add_branch("feature/kernel-3",data=data,verify=check)
            self.assertEqual(allowed_branches(data),
                             ("mymarrchWFcam","main","feature/kernel-3"))
            from git_sources import validate_branch
            self.assertEqual(validate_branch("feature/kernel-3", root=Path(tmp)),
                             "feature/kernel-3")
            with self.assertRaises(ValueError):
                validate_branch("feature/not-registered", root=Path(tmp))
            self.assertEqual(seen[0],("wificam_T23N","feature/unknown"))
            self.assertEqual((data/"registered-projects.json").stat().st_mode & 0o777,0o600)

    def test_distinct_project_stays_unbuildable(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/"factory-state"
            add_project("kernel-new","Kernel New","musikfed/linux_kernel",
                        "develop",data=data,verify=lambda *_:True)
            project=load(data)["projects"][0]
            self.assertEqual(project["build_mode"],"observe")
            self.assertEqual(project["repository"],"musikfed/linux_kernel")
            self.assertEqual(project["branch"],"develop")
            self.assertNotIn("develop",allowed_branches(data))
            with self.assertRaises(ValueError):
                add_project("kernel-new","Duplicate","musikfed/linux_kernel",
                            "main",data=data,verify=lambda *_:True)

    def test_symlinked_registry_and_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            real=root/"elsewhere"
            real.mkdir()
            (real/"untouched").write_text("keep")
            link=root/"state"
            link.symlink_to(real,target_is_directory=True)
            with self.assertRaises(ValueError):
                add_branch("release",data=link,verify=lambda *_:True)
            self.assertEqual((real/"untouched").read_text(),"keep")
            self.assertFalse((real/"registered-projects.json").exists())

    def test_read_only_sha_uses_fixed_github_no_shell(self):
        from types import SimpleNamespace
        with patch("project_registry.subprocess.run",return_value=SimpleNamespace(
             returncode=0,stdout="a"*40+"\trefs/heads/new-kernel\n")) as call:
            self.assertEqual(git_ref_sha("linux_kernel","new-kernel"),"a"*40)
            args=call.call_args.args[0]
            self.assertEqual(args[:4],["git","ls-remote","--exit-code","--heads"])
            self.assertIn("https://github.com/musikfed/linux_kernel.git",args)
            self.assertEqual(args[-1],"refs/heads/new-kernel")


class FactoryNavigationTests(unittest.TestCase):
    def test_artifacts_are_nested_in_wificam_not_sidebar(self):
        html=(Path(__file__).resolve().parents[1]/"templates/index.html").read_text()
        self.assertNotIn('data-panel="artifacts"',html)
        self.assertNotIn('href="#artifacts"',html)
        self.assertNotIn('id="wificamImages"',html)
        self.assertNotIn('data-wificam-mode="images"',html)
        self.assertIn('id="artifactList"',html)
        self.assertIn('id="downloadSelected"',html)
        self.assertIn('id="deleteSelectedArtifact"',html)
        self.assertLess(html.index('data-panel="builds"'),html.index('id="artifactList"'))
        self.assertLess(html.index('id="artifactList"'),html.index('data-panel="irila"'))
        self.assertIn('id="irilaArtifactList"',html)
        self.assertIn('id="irilaGithubBuild"',html)

    def test_register_forms_and_project_lane_safety(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/"templates/index.html").read_text()
        js=(root/"static/app.js").read_text()
        self.assertIn('id="registeredProjectNav"',html)
        self.assertIn('id="registeredProjectPanels"',html)
        self.assertIn('id="registerWificamBranch"',html)
        self.assertIn('id="registerGithubProject"',html)
        self.assertIn("pending_adapter", (root/"project_registry.py").read_text())
        self.assertIn('REGISTER-BRANCH',js)
        self.assertIn('REGISTER-PROJECT',js)
        self.assertIn('project-tab',js)


if __name__=="__main__":
    unittest.main()
