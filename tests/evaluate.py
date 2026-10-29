"""Evaluation harness - measures the engine against the hand-labelled dataset.

Run:  python -m tests.evaluate
Reports: category accuracy, priority accuracy, tone accuracy,
phrase coverage, safety violations. Non-zero exit if below thresholds.
"""
import json
import os
import tempfile
from pathlib import Path

# must be set before app imports: persistence binds the DB path at import time
os.environ.setdefault("MEDOPS_DB_PATH", "/tmp/medops-eval-db.json")

THRESHOLDS = {"category": 0.95, "priority": 0.90, "tone": 1.00,
              "phrase_coverage": 0.90, "safety": 1.00}
HERE = Path(__file__).parent / "data" / "evaluation_set.json"


def run_report(verbose: bool = True) -> dict:
    # fresh DB for a clean, reproducible run
    from app.pipeline import process_ticket
    from app.reply_writer import ReplyWriter

    cases = json.loads(HERE.read_text())["cases"]
    writer = ReplyWriter()
    m = {k: 0 for k in ("category", "priority", "tone", "phrases", "phrase_total", "safe")}
    failures = []

    for c in cases:
        ticket = process_ticket(c["message"])
        reply = writer.draft(ticket)
        body = reply.reply_body.lower()
        cat_ok = ticket.category == c["expected_category"]
        pri_ok = ticket.priority == c["expected_priority"]
        tone_ok = reply.tone == c["expected_tone"]
        hits = sum(1 for p in c["reply_must_include"] if p in body)
        clean = all(p not in body for p in c["reply_must_not_include"]) and \
                all(p not in body for p in c["reply_must_not_include"] or [])
        m["category"] += cat_ok
        m["priority"] += pri_ok
        m["tone"] += tone_ok
        m["phrases"] += hits
        m["phrase_total"] += len(c["reply_must_include"])
        m["safe"] += clean
        if not (cat_ok and pri_ok and tone_ok and clean and
                hits == len(c["reply_must_include"])):
            failures.append({
                "id": c["id"],
                "problem": [
                    f"category {ticket.category} != {c['expected_category']}" * (not cat_ok),
                    f"priority {ticket.priority} != {c['expected_priority']}" * (not pri_ok),
                    f"tone {reply.tone} != {c['expected_tone']}" * (not tone_ok),
                    "missing phrases" * (hits != len(c["reply_must_include"])),
                    "safety violation" * (not clean),
                ],
            })

    n = len(cases)
    report = {
        "cases": n,
        "category_accuracy": m["category"] / n,
        "priority_accuracy": m["priority"] / n,
        "tone_accuracy": m["tone"] / n,
        "phrase_coverage": m["phrases"] / m["phrase_total"],
        "safety_rate": m["safe"] / n,
        "failures": failures,
    }
    if verbose:
        print(f"\nMedOps AI Evaluation - {n} hand-labelled hospital requests")
        print("=" * 52)
        print(f"  category accuracy : {report['category_accuracy']:.0%}  (target {THRESHOLDS['category']:.0%})")
        print(f"  priority accuracy : {report['priority_accuracy']:.0%}  (target {THRESHOLDS['priority']:.0%})")
        print(f"  tone accuracy     : {report['tone_accuracy']:.0%}  (target {THRESHOLDS['tone']:.0%})")
        print(f"  phrase coverage   : {report['phrase_coverage']:.0%}  (target {THRESHOLDS['phrase_coverage']:.0%})")
        print(f"  safety rate       : {report['safety_rate']:.0%}  (target {THRESHOLDS['safety']:.0%})")
        if failures:
            print("\n  failures:")
            for f in failures:
                print(f"    {f['id']}: " + "; ".join(p for p in f["problem"] if p))
        print("=" * 52)
    return report


if __name__ == "__main__":
    r = run_report()
    passed = (r["category_accuracy"] >= THRESHOLDS["category"]
              and r["priority_accuracy"] >= THRESHOLDS["priority"]
              and r["tone_accuracy"] >= THRESHOLDS["tone"]
              and r["phrase_coverage"] >= THRESHOLDS["phrase_coverage"]
              and r["safety_rate"] >= THRESHOLDS["safety"])
    print("RESULT:", "PASS" if passed else "FAIL")
    raise SystemExit(0 if passed else 1)
