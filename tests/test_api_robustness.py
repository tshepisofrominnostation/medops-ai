"""API robustness: bad input gets descriptive 400s, never a 500 crash."""
import os
import tempfile

_path = tempfile.mktemp(suffix=".json")
os.environ.setdefault("MEDOPS_DB_PATH", _path)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_empty_message_gets_400():
    r = client.post("/tickets", json={"message": ""})
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_whitespace_message_gets_400():
    r = client.post("/tickets", json={"message": "   "})
    assert r.status_code == 400


def test_too_short_message_gets_400():
    r = client.post("/tickets", json={"message": "hi"})
    assert r.status_code == 400
    assert "short" in r.json()["detail"].lower()


def test_oversized_message_gets_400():
    r = client.post("/tickets", json={"message": "x" * 2500})
    assert r.status_code == 400
    assert "limit" in r.json()["detail"].lower()


def test_control_characters_gets_400():
    r = client.post("/tickets", json={"message": "valid text\x00\x01with junk"})
    assert r.status_code == 400
    assert "control" in r.json()["detail"].lower()


def test_malformed_json_body_gets_400_not_500():
    r = client.post("/tickets", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"] == "Bad Request"


def test_missing_message_field_gets_400():
    r = client.post("/tickets", json={"sender": "someone"})
    assert r.status_code == 400


def test_valid_ticket_still_works():
    r = client.post("/tickets", json={"message":
        '"The patient monitoring terminal in Bay 3 keeps disconnecting from the local network." - Dr. S. Khumalo (Emergency Ward)'})
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "IT & Medical Tech"
    assert body["priority"] == "High"
    assert set(body.keys()) == {"ticket_id", "timestamp", "sender", "category",
                                "priority", "summary", "assigned_to"}


def test_replies_endpoint_full_loop():
    r = client.post("/replies", json={"message":
        '"I need to apply for annual leave from 3 to 7 Dec." - Nurse T. Mokoena (Ward 5)'})
    assert r.status_code == 200
    data = r.json()
    assert data["ticket"]["category"] == "HR"
    assert data["reply"]["tone"] == "warm-administrative"
    assert "thank you" in data["reply"]["reply_body"].lower()


def test_replies_endpoint_rejects_bad_input():
    r = client.post("/replies", json={"message": ""})
    assert r.status_code == 400


def test_health_reports_engine():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["reply_writer"] in ("template", "llm")
