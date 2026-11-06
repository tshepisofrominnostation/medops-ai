"""The page's engine must agree with the Python service.

web/semantic.js and web/analytics.js are separate implementations of rules the service
owns. tests/data/app_parity.json is written by the Python code itself, so this compares
the two on real messages and real windows rather than on a promise.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
FIXTURES = ROOT / "tests" / "data" / "app_parity.json"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_browser_engine_matches_python():
    assert FIXTURES.exists(), "run python scripts/make_app_fixtures.py"
    result = subprocess.run(
        [NODE, str(ROOT / "scripts" / "check_app_parity.mjs")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "parity ok" in result.stdout


def test_fixtures_cover_the_awkward_cases():
    """A parity suite of easy sentences proves nothing; these cases must be in it."""
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    texts = " ".join(p["text"] for p in data["predictions"]).lower()
    assert "asdfgh" in texts, "needs a message with no usable vocabulary"
    assert "rekenaar" in texts, "needs a non-English message"
    assert any(p["phi"]["blocked"] for p in data["predictions"]), "needs a patient-data case"
    assert any(not p["confident"] for p in data["predictions"]), "needs a low-confidence case"
    assert len(data["analytics"]) >= 4, "needs several windows, including an empty one"
    assert any(w["value"]["total_tickets"] == 0 for w in data["analytics"]), "needs an empty window"
