#!/usr/bin/env python3
"""Offline PegineLab Project Contract v1 validator. Never executes build scripts."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_contract import validate_contract

def main() -> int:
    p=argparse.ArgumentParser(description="Validate a declarative PegineLab project contract without building anything.")
    p.add_argument("--manifest",required=True,type=Path)
    p.add_argument("--repo",required=True)
    p.add_argument("--branch",required=True)
    p.add_argument("--mode",required=True,choices=["build","observe"])
    a=p.parse_args()
    if a.manifest.is_symlink() or not a.manifest.is_file() or a.manifest.stat().st_size>32768:
        p.error("manifest must be a regular JSON file <=32 KiB")
    try:
        parsed=json.loads(a.manifest.read_text(encoding="utf-8"))
        validated=validate_contract(parsed,repo=a.repo,branch=a.branch,mode=a.mode)
    except (OSError,UnicodeError,ValueError) as exc:
        print("INVALID CONTRACT:",exc,file=sys.stderr)
        return 2
    print("VALID PEGineLab v1:",validated["project"]["name"],"mode:",a.mode)
    if a.mode=="build":
        print("Build execution: NOT authorized until factory-side adapter review")
    else:
        print("Observation integration: only declared, telemetry adapter not assumed")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
