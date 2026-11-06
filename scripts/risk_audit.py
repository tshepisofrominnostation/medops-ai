"""S3-3 risk audit: probe our own output and report what is actually wrong."""
import json, os, statistics
from pathlib import Path
os.environ.setdefault("MEDOPS_DB_PATH", "/tmp/risk.json")
Path(os.environ["MEDOPS_DB_PATH"]).unlink(missing_ok=True)

from app.compliance import screen
from app.forecast import forecast_volume
from app.pipeline import process_ticket
from app.reply_writer import ReplyWriter
from app.analytics import build_analytics

cases = json.load(open("tests/data/evaluation_set.json"))["cases"]
writer = ReplyWriter()
findings = []

# ---- probe 1: does our own reply writer trip our own compliance rules? ----
trips, checked = [], 0
for c in cases:
    try:
        t = process_ticket(c["message"])
        r = writer.draft(t)
        res = screen(getattr(r, "reply_body", ""))
        checked += 1
        if res["flags"]:
            trips.append({"case": c.get("id"), "verdict": res["verdict"],
                          "rules": [f["rule"] for f in res["flags"]],
                          "match": res["flags"][0]["match"]})
    except Exception as e:
        trips.append({"case": c.get("id"), "error": str(e)[:60]})
print(json.dumps({"probe": "compliance_vs_own_replies", "checked": checked,
                  "flagged": len(trips), "examples": trips[:4]}, indent=1))

# ---- probe 2: classifier accuracy on the labelled eval set ----
right = wrong = 0
misses = []
for c in cases:
    t = process_ticket(c["message"])
    if c.get("expected_category"):
        if t.category == c["expected_category"]: right += 1
        else:
            wrong += 1
            misses.append({"id": c.get("id"), "expected": c["expected_category"],
                           "got": t.category, "msg": c["message"][:58]})
print(json.dumps({"probe": "classifier_accuracy", "right": right, "wrong": wrong,
                  "pct": round(100*right/max(1, right+wrong), 1), "misses": misses[:4]}, indent=1))

# ---- probe 3: is the forecast better than a naive average? ----
import random
rnd = random.Random(3)
def series(kind):
    if kind == "flat": return [5]*20
    if kind == "noisy": return [rnd.randint(1, 9) for _ in range(20)]
    return [2+i//3 for i in range(20)]
rows = []
for kind in ("flat", "noisy", "trending"):
    vals = series(kind)
    hist = [{"date": f"2026-10-{i+1:02d}", "count": v} for i, v in enumerate(vals)]
    out = forecast_volume(hist, horizon=5)
    naive = statistics.mean(vals[-5:])
    model_err = statistics.mean(abs(f["predicted"] - vals[-1]) for f in out["forecast"])
    rows.append({"series": kind, "backtest_mae": out["backtest_mae"],
                 "naive_level": round(naive, 2), "model_vs_last": round(model_err, 2)})
print(json.dumps({"probe": "forecast_vs_naive", "rows": rows}, indent=1))

# ---- probe 4: do undated records disappear from analytics? ----
recs = [{"ticket_id": "MED-1", "category": "HR", "priority": "High", "assigned_to": "HR Admin Team"},
        {"ticket_id": "MED-2", "category": "HR", "priority": "Low", "assigned_to": "HR Admin Team",
         "timestamp": "2026-11-05T09:00:00+00:00"}]
d = build_analytics(recs)
print(json.dumps({"probe": "undated_records", "records": 2, "counted": d["total_tickets"],
                  "by_day": d["by_day"]}, indent=1))
