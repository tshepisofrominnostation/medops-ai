"""The published console page must generate a ticket and move its own dashboard.

Runs the real built HTML in a headless DOM (jsdom) and asserts the page's contract:
a generated ticket gets an id, is classified by the ported engine, is routed, appears
in the ticket table, moves the KPI tiles and the mix charts, survives a reload, obeys
the filters, and can be cleared. Skipped when node or jsdom is unavailable.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
PAGE = ROOT / "docs" / "console" / "index.html"


def _jsdom_available() -> bool:
    if NODE is None:
        return False
    probe = subprocess.run(
        [NODE, "-e", "require('jsdom')"], cwd=ROOT, capture_output=True
    )
    return probe.returncode == 0


@pytest.mark.skipif(not _jsdom_available(), reason="node + jsdom not installed; run npm install")
def test_published_console_behaves():
    assert PAGE.exists(), "build the page first: python scripts/build_pages.py"
    result = subprocess.run(
        [NODE, str(ROOT / "scripts" / "check_console.mjs"), str(PAGE)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "console page ok" in result.stdout
