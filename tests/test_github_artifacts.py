"""GitHub Actions scope: only pinned repos/workflow and explicit artifact ID."""
import json
import os
import unittest
from unittest.mock import patch
from github_artifacts import list_artifacts, delete_artifact, dispatch_irila

class GithubArtifactTests(unittest.TestCase):
    def test_irila_dispatch_only_approved_workflow_and_branch(self):
        with patch("github_artifacts.gh",return_value="") as gh:
            dispatch_irila()
            self.assertEqual(gh.call_args.args[0],
                ["workflow","run","build-installed-full-secureboot-img.yml",
                 "--repo","musikfed/Irila_baikal_v1.0","--ref","main"])

    def test_no_unknown_project_or_id(self):
        with patch("github_artifacts.gh") as gh:
            with self.assertRaises(ValueError):
                list_artifacts("some-other-repo")
            with self.assertRaises(ValueError):
                delete_artifact("irila","../../123")
            gh.assert_not_called()

    def test_artifact_listing_returns_scoped_links_only(self):
        fake=[{"id":102,"name":"irila-img","size_in_bytes":4096,
               "expired":False,"created_at":"2026-11-04T00:00:00Z",
               "workflow_run":{"id":123,"head_sha":"a"*40}}]
        with patch("github_artifacts.gh",return_value=json.dumps(fake)) as gh:
            items=list_artifacts("irila")
            self.assertEqual(items[0]["id"],102)
            self.assertEqual(items[0]["url"],
                             "https://github.com/musikfed/Irila_baikal_v1.0/actions/runs/123")
            self.assertEqual(gh.call_args.args[0][1],
                             "repos/musikfed/Irila_baikal_v1.0/actions/artifacts?per_page=60")

    def test_delete_requires_explicit_server_opt_in_and_exact_repo(self):
        fake=[{"id":102,"name":"expected"}]
        with patch("github_artifacts.gh",return_value=json.dumps(fake)) as gh:
            with patch.dict(os.environ,{"PEGINELAB_GITHUB_ARTIFACT_DELETE":"0"}):
                with self.assertRaises(ValueError):
                    delete_artifact("irila","102")
            gh.assert_not_called()
        with patch.dict(os.environ,{"PEGINELAB_GITHUB_ARTIFACT_DELETE":"1"}):
            with patch("github_artifacts.list_artifacts",return_value=[{"id":102}]):
                with patch("github_artifacts.gh",return_value="") as gh:
                    delete_artifact("irila","102")
                    self.assertEqual(gh.call_args.args[0],
                        ["api","-X","DELETE",
                         "repos/musikfed/Irila_baikal_v1.0/actions/artifacts/102"])
                with patch("github_artifacts.gh") as gh:
                    with self.assertRaises(ValueError):
                        delete_artifact("irila","999")
                    gh.assert_not_called()

if __name__=="__main__":
    unittest.main()
