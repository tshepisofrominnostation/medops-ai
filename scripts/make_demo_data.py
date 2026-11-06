"""Generate a reproducible, clearly synthetic ticket history for demos and screenshots.

Runs every message through the REAL pipeline (parser, classifier, prioritiser,
assigner), so categories, priorities and routing are the engine's own. Only the
timestamps and the lifecycle (first response, resolution) are simulated.

    python scripts/make_demo_data.py --out data/demo_tickets.json --days 21

It never touches data/tickets_processed.json. To use it, point the API at it:

    MEDOPS_DB_PATH=data/demo_tickets.json uvicorn app.main:app

Every record carries "synthetic": true so demo data can never be mistaken for real.
"""
import argparse
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MESSAGES = [
    ('"The patient monitoring terminal in Bay 3 keeps disconnecting from the network." - Dr. S. Khumalo (Emergency Ward)', "IT"),
    ('"Ventilator alarm panel is not responding in ICU." - Sr. T. Mokoena (ICU)', "IT"),
    ('"The EMR login keeps timing out on the ward computers." - Nurse P. Dube (Ward 4)', "IT"),
    ('"Wifi is down in the maternity corridor." - Sr. L. Naidoo (Maternity)', "IT"),
    ('"Telemetry server crashed and the cardiac unit is offline." - Dr. A. Pillay (Cardiology)', "IT"),
    ('"My payslip shows the wrong overtime hours for October." - Nurse K. Zulu (Ward 2)', "HR"),
    ('"Requesting annual leave from 1 to 5 December." - Dr. M. Sithole (Paediatrics)', "HR"),
    ('"We are short two nurses on the night roster this weekend." - Sr. N. Khoza (Surgical Ward)', "HR"),
    ('"Please confirm my contract renewal." - Mr. J. Botha (Radiology)', "HR"),
    ('"Recruitment for the ward manager post needs interview dates." - Ms. R. Govender (HR Office)', "HR"),
    ('"Supplier invoice from August is still unpaid, delivery is at risk." - Mr. D. Mahlangu (Procurement)', "FIN"),
    ('"Medical aid rejected the claim for a surgical admission." - Ms. C. Ndlovu (Billing)', "FIN"),
    ('"We need a purchase approved before the budget closes." - Dr. F. Jacobs (Theatre)', "FIN"),
    ('"Reimbursement for conference travel expenses is outstanding." - Mr. W. Smit (Admin)', "FIN"),
    ('"A patient was billed twice for the same procedure." - Ms. B. Radebe (Accounts)', "FIN"),
    ('"The aircon in Theatre 2 has stopped working." - Dr. Naidoo (Theatre 2)', "OPS"),
    ('"Water is leaking in the staff kitchen." - Mr. S. Cele (Catering)', "OPS"),
    ('"The generator did not start during the power outage." - Mr. H. Nkosi (Maintenance)', "OPS"),
    ('"The lift between floors 1 and 4 is stuck again." - Ms. E. Venter (Reception)', "OPS"),
    ('"Several corridor lights have burnt out in Block C." - Mr. T. Molefe (Security)', "OPS"),
    ('"Cleaning has not been done in Ward 6 today." - Sr. G. Mthembu (Ward 6)', "OPS"),
    ('"Gas leak smell near the boiler room, please act immediately." - Mr. Y. Ismail (Maintenance)', "OPS"),
]
# Realistic skew: more IT and Ops than HR/Finance, with a mid-period surge.
WEIGHT = {"IT": 0.34, "HR": 0.18, "FIN": 0.18, "OPS": 0.30}
# Simulated first-response behaviour by priority: (median minutes, spread, chance of never answered)
RESPONSE = {"High": (11, 9, 0.02), "Medium": (95, 70, 0.05), "Low": (330, 260, 0.08)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/demo_tickets.json")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--end", default=None, help="last day, YYYY-MM-DD (default: today)")
    a = ap.parse_args()

    rnd = random.Random(a.seed)
    tmp = Path(tempfile.mkdtemp()) / "scratch.json"
    os.environ["MEDOPS_DB_PATH"] = str(tmp)
    from app.pipeline import process_ticket   # the real engine

    end = datetime.fromisoformat(a.end).date() if a.end else datetime.now().date()
    tz = timezone(timedelta(hours=2))
    rows = []
    for offset in range(a.days):
        day = end - timedelta(days=a.days - 1 - offset)
        if day.weekday() >= 5:
            n = rnd.randint(1, 3)                      # quieter weekends
        else:
            n = rnd.randint(3, 7)
        if a.days // 2 <= offset <= a.days // 2 + 2:    # a three-day surge
            n += rnd.randint(3, 5)
        for _ in range(n):
            pool = [m for m in MESSAGES]
            grp = rnd.choices(list(WEIGHT), weights=list(WEIGHT.values()))[0]
            msg = rnd.choice([m for m in pool if m[1] == grp])[0]
            t = process_ticket(msg)
            rec = t.model_dump()
            created = datetime(day.year, day.month, day.day, rnd.randint(6, 17),
                               rnd.randint(0, 59), tzinfo=tz)
            rec["timestamp"] = created.isoformat(timespec="seconds")
            med, spread, never = RESPONSE[rec["priority"]]
            if rnd.random() >= never:
                resp = max(1.0, rnd.gauss(med, spread))
                first = created + timedelta(minutes=resp)
                rec["first_response_at"] = first.isoformat(timespec="seconds")
                rec["status"] = "In Progress"
                if rnd.random() < 0.7:
                    done = first + timedelta(minutes=max(5, rnd.gauss(med * 2.5, med)))
                    rec["resolved_at"] = done.isoformat(timespec="seconds")
                    rec["status"] = "Resolved"
            else:
                rec["status"] = "Open"
            rec["synthetic"] = True
            rows.append(rec)
    for i, r in enumerate(rows, 1):
        r["ticket_id"] = f"MED-{i:03d}"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(rows)} synthetic tickets over {a.days} days to {a.out}")


if __name__ == "__main__":
    main()
