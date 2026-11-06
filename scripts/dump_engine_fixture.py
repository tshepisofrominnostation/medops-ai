"""Record what the Python engine does, so the browser port can be held to it.

Writes tests/data/engine_parity.json: inputs plus the exact category, confidence,
priority, route, sender and summary that app/ produced for each one.

The corpus is deliberately broader than the demo data:
  * every seeded ticket message (the text the pipeline actually sees in a shift)
  * every labelled evaluation case
  * hand-written edges: empty and whitespace-only input, no keywords at all, all caps,
    repeated keywords, more than 22 words, a "From:" header, the signed-off form,
    accented names, and clinical-plus-routine wording that should de-escalate.

Run:  python scripts/dump_engine_fixture.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MEDOPS_DB_PATH", str(ROOT / "data" / "demo_tickets.json"))

from app.assigner import assign            # noqa: E402
from app.classifier import classify        # noqa: E402
from app.parser import parse_sender        # noqa: E402
from app.prioritizer import prioritize     # noqa: E402
from app.summarizer import summarize       # noqa: E402

OUT = Path(os.environ.get("MEDOPS_PARITY_OUT", ROOT / "tests" / "data" / "engine_parity.json"))

EDGES = [
    "",
    "   ",
    "Hello",
    "hello there, just checking in",
    "THE GENERATOR HAS NO POWER AND THE ICU IS DARK",
    "aircon aircon aircon aircon in theatre 3",
    "The ward printer keeps jamming and nobody has looked at it since Tuesday morning "
    "which means the nursing staff are writing out drug charts by hand and the pharmacy "
    "cannot reconcile them until somebody resets the print spooler on that machine",
    "From: Sister Naidoo\n\nThe telemetry is down in ICU.",
    "Bedside monitor offline in Bay 4 - Mr Pillay (ICU)",
    "Sister Chloé du Pré - Équipe (Théâtre 2)",
    "Invoice 4471 query for the monthly query cycle, no rush",
    "Fire alarm panel beeping in Block B, staff short two on the ward tonight",
    "Medfusion pump will not start, patient on it now, theatre 1",
    "Mr Dlamini in bed 12 has been waiting since Monday - Dr Naidoo (Ward 4)",
    "  \"  payslip shows an overpayment, please query  \"  ",
]


def keyword_probes() -> list[str]:
    """One probe per learned term, so a divergence in any table entry is caught.

    Without these the corpus only exercises the words that happen to appear in the
    labelled examples, which is exactly where a hand-ported table drifts unnoticed.
    """
    from app.classifier import CATEGORY_KEYWORDS
    from app.prioritizer import (
        CLINICAL_CONTEXT, CLINICAL_EQUIPMENT, ROUTINE, SAFETY,
        STAFFING_CRITICAL, URGENT,
    )

    probes = []
    for keywords in CATEGORY_KEYWORDS.values():
        for keyword in keywords:
            term = keyword.strip()
            probes.append(f"Please check the {term} problem")
            probes.append(f"{term} {term} has failed again")
    for group in (CLINICAL_CONTEXT, CLINICAL_EQUIPMENT, SAFETY, URGENT, STAFFING_CRITICAL, ROUTINE):
        for term in group:
            probes.append(f"{term} in ward 3")
            probes.append(f"the {term} issue needs attention - Staff Member (Ward 3)")
    for hazard in SAFETY:
        for equipment in CLINICAL_EQUIPMENT:
            probes.append(f"{hazard} and the {equipment} is affected")
    return probes


def corpus() -> list[dict]:
    rows = [{"message": text} for text in EDGES]
    rows += [{"message": text} for text in keyword_probes()]

    # The seeded store keeps summaries and senders, not the raw message, so replay the
    # summary text: it is real engine output phrased the way staff write.
    store = json.loads((ROOT / "data" / "demo_tickets.json").read_text())
    tickets = store["tickets"] if isinstance(store, dict) else store
    rows += [{"message": t["summary"]} for t in tickets if t.get("summary")]

    cases = json.loads((ROOT / "tests" / "data" / "evaluation_set.json").read_text())["cases"]
    for case in cases:
        text = case.get("message") or case.get("text") or case.get("input")
        if text:
            rows.append({"message": text})
    return rows


def main() -> None:
    recorded = []
    for row in corpus():
        body, sender = parse_sender(row["message"])
        category, confidence = classify(body)
        priority = prioritize(body, sender)
        recorded.append({
            "message": row["message"],
            "expect": {
                "body": body,
                "sender": sender,
                "category": category,
                "confidence": confidence,
                "priority": priority,
                "assigned_to": assign(category, priority),
                "summary": summarize(body, sender, category, priority),
            },
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"cases": recorded}, indent=1) + "\n")
    try:
        shown = OUT.relative_to(ROOT)
    except ValueError:          # tests write to a temp dir outside the repo
        shown = OUT
    print(f"recorded {len(recorded)} messages -> {shown}")


if __name__ == "__main__":
    main()
