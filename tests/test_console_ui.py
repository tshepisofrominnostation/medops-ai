"""The operations console must render and its buttons must work.

This runs the real API in a background thread and drives console.py through
Streamlit's AppTest harness, so a broken chart, a bad widget argument or a dead
button fails the suite instead of being found by a demonstrator.
"""
import os
import socket
import threading
import time

import pytest

pytest.importorskip("streamlit")
streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from pathlib import Path

CONSOLE = str(Path(__file__).resolve().parent.parent / "console.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_api(tmp_path_factory):
    """A real uvicorn server on a free port, seeded with a few tickets."""
    import uvicorn
    from app.main import app as api_app

    db = tmp_path_factory.mktemp("ui") / "tickets.json"
    os.environ["MEDOPS_DB_PATH"] = str(db)
    import app.persistence as persistence
    persistence.DB_PATH = db

    port = _free_port()
    config = uvicorn.Config(api_app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    import requests
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            requests.get(f"{base}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        pytest.skip("API did not start")

    for msg in ('"The patient monitoring terminal in Bay 3 keeps disconnecting." '
                '- Dr. S. Khumalo (Emergency Ward)',
                '"The aircon in Theatre 2 is not working." - Dr. Naidoo (Theatre 2)',
                '"My payslip shows the wrong overtime hours." - Nurse K. Zulu (Ward 2)'):
        requests.post(f"{base}/tickets", json={"message": msg}, timeout=10)

    os.environ["MEDOPS_API_URL"] = base
    yield base
    server.should_exit = True
    thread.join(timeout=5)
    os.environ.pop("MEDOPS_API_URL", None)


def _apptimeout():
    return AppTest.from_file(CONSOLE, default_timeout=180)


def test_console_renders_every_tab(live_api):
    at = _apptimeout().run()
    assert not at.exception, [e.value for e in at.exception]
    assert [t.value for t in at.title] == [
        "Log a hospital request", "Work the queue", "Weekly insight", "Weekly reports"]
    assert len(at.tabs) == 4


def test_intake_classifies_and_drafts(live_api):
    at = _apptimeout().run()
    at.text_area[0].set_value('"The ventilator alarm panel in ICU is not responding." '
                              '- Sr. T. Mokoena (ICU)')
    [b for b in at.button if "Classify" in b.label][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    for expected in ("Drafted reply", "Safety screen", "Second opinion", "IT & Medical Tech"):
        assert expected in md, expected


def test_queue_buttons_move_a_ticket(live_api):
    import requests
    before = {r["ticket_id"]: r["status"]
              for r in requests.get(f"{live_api}/tickets", timeout=10).json()}
    open_ids = [k for k, v in before.items() if v == "Open"]
    assert open_ids, "fixture should leave at least one Open ticket"

    at = _apptimeout().run()
    starts = [b for b in at.button if b.label.strip().endswith("Start")]
    assert starts, "no Start button rendered for an Open ticket"
    starts[0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]

    after = {r["ticket_id"]: r["status"]
             for r in requests.get(f"{live_api}/tickets", timeout=10).json()}
    moved = [k for k in after if before.get(k) != after[k]]
    assert moved, "clicking Start changed nothing"
    assert after[moved[0]] == "In Progress"


def test_insight_tab_shows_findings_and_its_limits(live_api):
    at = _apptimeout().run()
    md = " ".join(m.value for m in at.markdown)
    assert "Executive summary" in md
    assert "Findings and their evidence" in md
    assert "cannot tell you" in md, "the limits note must always be shown"


def test_reports_tab_produces_three_downloads(live_api):
    at = _apptimeout().run()
    [b for b in at.button if b.label.strip() == "Generate"][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [d.label for d in at.get("download_button")]
    assert any("PDF" in l for l in labels)
    assert any("CSV" in l for l in labels)
    assert any("JSON" in l for l in labels)


def test_console_explains_a_dead_api_instead_of_showing_empty_charts(monkeypatch):
    """The worst failure mode is a blank screen that looks like zero tickets."""
    monkeypatch.setenv("MEDOPS_API_URL", "http://127.0.0.1:9")   # discard port
    at = _apptimeout().run()
    md = " ".join(m.value for m in at.markdown)
    assert "Cannot reach the MedOps API" in md
    assert "uvicorn app.main:app" in md


# ---------------------------------------------------------------------------
# Single-service mode: the console deployed as one Streamlit app, no API server.
# ---------------------------------------------------------------------------

def test_in_process_mode_needs_no_api_server(monkeypatch):
    """Unsetting MEDOPS_API_URL runs the engine in-process, so the UI can be hosted
    alone. Same routes, same numbers, just a local transport."""
    monkeypatch.delenv("MEDOPS_API_URL", raising=False)
    monkeypatch.setenv("MEDOPS_DB_PATH", str(_fresh_store()))
    at = AppTest.from_file(CONSOLE, default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    assert "Single-service mode" in md
    assert any(c.value == "API: `in-process`" for c in at.caption)


def test_in_process_intake_works(monkeypatch):
    monkeypatch.delenv("MEDOPS_API_URL", raising=False)
    monkeypatch.setenv("MEDOPS_DB_PATH", str(_fresh_store()))
    at = AppTest.from_file(CONSOLE, default_timeout=180).run()
    at.text_area[0].set_value('"The ventilator alarm panel in ICU is not responding." '
                              '- Sr. T. Mokoena (ICU)')
    [b for b in at.button if "Classify" in b.label][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    assert "Drafted reply" in md
    assert "IT & Medical Tech" in md


def test_demo_history_button_only_on_an_empty_store(monkeypatch):
    """A hosted demo must not present synthetic data as if it were pre-existing fact."""
    monkeypatch.delenv("MEDOPS_API_URL", raising=False)
    store = _fresh_store()
    monkeypatch.setenv("MEDOPS_DB_PATH", str(store))

    at = AppTest.from_file(CONSOLE, default_timeout=180).run()
    buttons = [b for b in at.button if b.label == "Load demo history"]
    assert buttons, "empty store should offer the demo loader"

    buttons[0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert not any(b.label == "Load demo history" for b in at.button)

    import json
    rows = json.loads(store.read_text())
    assert len(rows) > 50
    assert all(r.get("synthetic") is True for r in rows), "demo data must stay labelled"


def _fresh_store():
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp(prefix="medops-ui-")) / "tickets.json"
