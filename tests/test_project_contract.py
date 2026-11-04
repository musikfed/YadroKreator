"""Project Contract v1: build request is descriptive; no arbitrary shell execution."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from project_contract import validate_contract, read_contract
from project_registry import add_project,load

SHA="a"*40
REPO="musikfed/kernel_lab"

def manifest(mode="build"):
    obj={
       "schema":"peginelab.project.v1",
       "project":{"name":"Kernel Lab","repository":REPO,"branch":"main","mode":mode},
       "platform":{"architecture":"mipsel","board":"Ingenic T23N",
                   "toolchain":"mipsel-linux-musl"},
       "targets":["t23n"],
       "outputs":[{"type":"img","path":"out/firmware.img"}],
       "monitoring":{"signals":["build_status","artifact_sha256"]},
       "docs":["README.md","docs/BUILD_RU.md"],
       "extensions":{"peginelab.camera":{"sensor":"SC2336"}}
    }
    if mode=="build":
       obj["pipeline"]={"adapter":"thingino_t23n_v1",
                         "entrypoint":"scripts/build-image.sh"}
    return obj


class ContractTests(unittest.TestCase):
    def test_valid_t23n_recipe_is_not_auto_executable(self):
        item=validate_contract(manifest(),repo=REPO,branch="main",mode="build")
        self.assertEqual(item["pipeline"]["adapter"],"thingino_t23n_v1")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            add_project("kernel-lab","Kernel Lab",REPO,"main",mode="build",
                        data=root,verify=lambda *_:True,source_sha=SHA,
                        manifest=manifest())
            entry=load(root)["projects"][0]
            self.assertEqual(entry["build_mode"],"pending_adapter")
            self.assertEqual(entry["contract"]["source_sha"],SHA)
            self.assertEqual(entry["contract"]["outputs"][0]["path"],"out/firmware.img")

    def test_observation_is_explicit_and_never_a_build(self):
        valid=validate_contract(manifest("observe"),repo=REPO,branch="main",mode="observe")
        self.assertEqual(valid["project"]["mode"],"observe")
        with tempfile.TemporaryDirectory() as tmp:
            add_project("kernel-lab","Observe Lab",REPO,"main",mode="observe",
                        data=Path(tmp),verify=lambda *_:True)
            item=load(Path(tmp))["projects"][0]
            self.assertEqual(item["build_mode"],"observe")
            self.assertIsNone(item["contract"])

    def test_invalid_paths_or_mismatched_origin_refused(self):
        for value in ("../etc/shadow","/tmp/evil","foo/../bar","foo;rm -rf .",
                      "https://evil.example/test","foo/.git/config"):
            d=manifest()
            d["pipeline"]["entrypoint"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_contract(d,repo=REPO,branch="main",mode="build")
        d=manifest()
        d["project"]["repository"]="other/kernel_lab"
        with self.assertRaises(ValueError):
            validate_contract(d,repo=REPO,branch="main",mode="build")
        d=manifest()
        d["pipeline"]={"adapter":"sh -c curl evil"}
        with self.assertRaises(ValueError):
            validate_contract(d,repo=REPO,branch="main",mode="build")

    def test_missing_contract_refuses_build_registration_without_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("project_registry.read_contract",side_effect=ValueError("not found")):
                with self.assertRaises(ValueError):
                    add_project("kernel-lab","Kernel Lab",REPO,"main",mode="build",
                                data=Path(tmp),verify=lambda *_:True,source_sha=SHA)
            self.assertFalse((Path(tmp)/"registered-projects.json").exists())

    def test_remote_url_is_one_fixed_host_and_pinned_sha(self):
        from unittest.mock import MagicMock
        response=MagicMock()
        response.geturl.return_value=f"https://raw.githubusercontent.com/{REPO}/{SHA}/peginelab.project.json"
        response.read.return_value=b'{"schema":"peginelab.project.v1"}'
        response.__enter__.return_value=response
        with patch("project_contract.build_opener") as op:
            op.return_value.open.return_value=response
            out=read_contract(REPO,"main",SHA)
            self.assertEqual(out["schema"],"peginelab.project.v1")
            req=op.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url,response.geturl.return_value)
        with self.assertRaises(ValueError):
            read_contract("evil/repo","main",SHA)


if __name__=="__main__":
    unittest.main()
