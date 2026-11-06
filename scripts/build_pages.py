"""Build the published page: one HTML file, no runtime dependencies.

The page is assembled from web/page.html plus the modules in web/, with the Python
service's model bundle inlined (scripts/build_app_bundle.py). Inlining is deliberate:
GitHub Pages serves static files, and a page that needs a second request to become
interactive is a page that breaks quietly when that request fails.

    python scripts/build_pages.py [--out docs]

Also refreshes data derived artifacts (report.pdf/csv/json) and leaves a redirect at
docs/console/ so the old URL keeps working after the pages were merged into one.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WEB = ROOT / "web"

# In order: the data layer, the engine, the view. Each file attaches itself to window.
MODULES = ["analytics.js", "semantic.js", "app.js", "ui.js"]


def _bundle() -> dict:
    from scripts.build_app_bundle import build
    return build()


def _read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def build(out_dir: Path) -> Path:
    bundle = _bundle()
    app_js = "\n".join(f"/* ---- {name} ---- */\n{_read(name)}" for name in MODULES)

    html = _read("page.html")
    # json.dumps keeps the payload from breaking out of the <script> tag.
    html = html.replace("__BUNDLE__", json.dumps(bundle).replace("</", "<\\/"))
    html = html.replace("__APP_JS__", app_js)

    stamped = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    html = html.replace(
        '<span id="footmeta"></span>',
        f'<span id="footmeta"></span><span class="tiny"> · built {stamped}</span>',
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    page = out_dir / "index.html"
    page.write_text(html, encoding="utf-8")

    _retire_console_page(out_dir)
    _write_artifacts(out_dir)
    return page


def _retire_console_page(out_dir: Path) -> None:
    """docs/console/ used to be a separate snapshot page. One app now: send it home."""
    legacy = out_dir / "console"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "index.html").write_text(
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>MedOps AI</title>"
        "<meta http-equiv=\"refresh\" content=\"0; url=../\">"
        "<link rel=\"canonical\" href=\"../\">"
        "</head><body style=\"background:#0a1628;color:#e2e8f0;font-family:system-ui;padding:40px\">"
        "<p>The console and the dashboard are now one page. "
        "<a style=\"color:#22d3ee\" href=\"../\">Continue to MedOps AI →</a></p>"
        "</body></html>\n",
        encoding="utf-8",
    )


def _write_artifacts(out_dir: Path) -> None:
    """The Week 4 report, rendered from the committed store, next to the page."""
    try:
        from fastapi.testclient import TestClient

        from app.main import app
    except Exception as exc:                      # pragma: no cover - artifacts are optional
        print(f"artifacts skipped: {exc}")
        return

    client = TestClient(app)
    target = out_dir / "artifacts"
    target.mkdir(parents=True, exist_ok=True)
    for name, path in (("report.pdf", "/report.pdf"), ("report.csv", "/report.csv"),
                       ("report.json", "/report")):
        try:
            resp = client.get(path)
            if resp.status_code == 200:
                (target / name).write_bytes(resp.content)
                print(f"artifact {name}: {len(resp.content) / 1024:.0f} KB")
            else:
                print(f"artifact {name}: HTTP {resp.status_code}, skipped")
        except Exception as exc:                  # pragma: no cover
            print(f"artifact {name}: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs"))
    args = ap.parse_args()
    page = build(Path(args.out))
    size = page.stat().st_size
    print(f"wrote {page} ({size / 1024:.0f} KB)")
    arts = sorted(p.name for p in (Path(args.out) / "artifacts").glob("*")) if (Path(args.out) / "artifacts").exists() else []
    if arts:
        print("artifacts:", ", ".join(arts))


if __name__ == "__main__":
    main()
