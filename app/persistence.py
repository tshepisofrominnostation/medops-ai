"""Persistence — append-only local database (data/tickets_processed.json)."""
import json
import os
import threading
from pathlib import Path

DB_PATH = Path(os.environ.get("MEDOPS_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "tickets_processed.json")))
_lock = threading.Lock()


def load_all() -> list[dict]:
    if not DB_PATH.exists():
        return []
    with DB_PATH.open() as f:
        return json.load(f)


def append(record: dict) -> dict:
    with _lock:
        rows = load_all()
        if not record.get("ticket_id"):
            record["ticket_id"] = f"MED-{len(rows) + 1:03d}"
        rows.append(record)
        DB_PATH.parent.mkdir(exist_ok=True)
        with DB_PATH.open("w") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    return record
