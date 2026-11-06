"""The published page must work as one app, not as three features in a trenchcoat.

Runs the built docs/index.html in a headless DOM and performs the user's journey:
read the seeded dashboard, log a request, check the ticket card explains itself, watch
the dashboard and weekly summary move, resolve, then clear. Skipped without node+jsdom.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
PAGE = ROOT / "docs" / "index.html"


def _jsdom() -> bool:
    if NODE is None:
        return False
    return subprocess.run([NODE, "-e", "require('jsdom')"], cwd=ROOT,
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not _jsdom(), reason="node + jsdom not installed; run npm install")
def test_published_page_journey():
    assert PAGE.exists(), "build the page first: python scripts/build_pages.py"
    result = subprocess.run([NODE, str(ROOT / "scripts" / "check_app.mjs"), str(PAGE)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "page ok" in result.stdout


def test_page_is_self_contained():
    """One file, no second request: a CDN or a separate .js file would break offline."""
    html = PAGE.read_text(encoding="utf-8")
    assert "<script src=" not in html, "page must not load an external script"
    assert "cdn.tailwindcss.com" not in html
    assert "medops.week3.store.v1" in html
    # Every module is inlined, in dependency order.
    order = [html.index("MedOpsAnalytics"), html.index("MedOpsSemantic"),
             html.index("MedOpsApp"), html.index("__medops")]
    assert order == sorted(order)


def test_legacy_console_url_redirects():
    legacy = ROOT / "docs" / "console" / "index.html"
    assert legacy.exists()
    assert "url=../" in legacy.read_text(encoding="utf-8")
