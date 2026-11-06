"""The page's "Export for import" must be accepted by the Python importer.

Two languages, one contract: web/export.js writes the file, app/importer.py reads it.
Testing each side alone proves nothing about the pair, so this runs the real JavaScript
and feeds its real output to the real importer.

Skipped when Node is unavailable.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import persistence
from app.importer import import_tickets

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")

SAMPLE = [{
    "id": "MED-WEB-01",
    "created_at": "2026-11-06T10:02:00Z",
    "message": "The ventilator in ICU Bay 3 is alarming and will not start.",
    "sender": "Sister Naidoo (ICU)",
    "category": "IT & Medical Tech",
    "priority": "High",
    "assigned_to": "IT & Biomedical Engineering on-call",
    "summary": "The ventilator in ICU Bay 3 is alarming and will not start. Reported by ICU; "
               "classified as IT & Medical Tech with High priority.",
    "status": "Open",
}]


def _run_export(kind: str, tickets) -> str:
    script = (
        "const fs=require('fs');"
        f"const M=eval(fs.readFileSync({json.dumps(str(ROOT / 'web' / 'export.js'))},'utf8')"
        "+';MedOpsExport');"
        "const tickets=JSON.parse(fs.readFileSync(0,'utf8'));"
        f"process.stdout.write(M.{kind}(tickets));"
    )
    result = subprocess.run([NODE, "-e", script], input=json.dumps(tickets),
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "tickets.json"
    path.write_text("[]")
    monkeypatch.setattr(persistence, "DB_PATH", path)
    return path


@pytest.mark.skipif(NODE is None, reason="node is not installed; export contract unchecked")
def test_page_export_imports_cleanly(store):
    payload = json.loads(_run_export("toExport", SAMPLE))
    report = import_tickets(payload)
    assert report["summary"]["rejected"] == 0, report["rejected"]
    assert report["summary"]["added"] == 1
    stored = json.loads(store.read_text())[0]
    assert stored["sender"] == "Sister Naidoo (ICU)"
    assert stored["category"] == "IT & Medical Tech"
    assert stored["priority"] == "High"
    assert stored["status"] == "Open"
    assert stored["timestamp"] == "2026-11-06T10:02:00Z"
    assert stored["synthetic"] is False


@pytest.mark.skipif(NODE is None, reason="node is not installed; export contract unchecked")
def test_csv_export_has_one_row_per_ticket_and_quotes_commas(store):
    tricky = dict(SAMPLE[0], summary="Pump failed, patient moved, ward informed.")
    csv_text = _run_export("toCsv", [SAMPLE[0], tricky])
    lines = csv_text.strip().split("\n")
    assert len(lines) == 3                       # header + two tickets
    assert lines[0].startswith("ticket_id,timestamp,sender")
    assert "Pump failed, patient moved, ward informed." in lines[2]
    assert lines[2].count('"') % 2 == 0          # every quote is balanced
