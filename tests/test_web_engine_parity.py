"""The published page runs the engine in the browser, so it must agree with Python.

web/engine.js is a port. A port without a test is a second implementation of the
business rules, and the two drift the first time someone edits a keyword table. This
replays the recorded corpus through both and fails on any difference in category,
confidence, priority, route, sender, body or summary.

Skipped when Node is unavailable (it is not a runtime dependency of the service).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed; browser engine unchecked")
def test_browser_engine_matches_python(tmp_path):
    sys.path.insert(0, str(ROOT))
    from scripts.engine_bundle import build_bundle

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(build_bundle()))

    fixture_path = tmp_path / "parity.json"
    env = dict(os.environ, MEDOPS_PARITY_OUT=str(fixture_path))
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dump_engine_fixture.py")],
        check=True, cwd=ROOT, env=env, capture_output=True,
    )
    assert fixture_path.exists(), "fixture was not written"

    result = subprocess.run(
        [NODE, str(ROOT / "scripts" / "check_engine_parity.mjs"),
         str(bundle_path), str(fixture_path)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "parity ok" in result.stdout
