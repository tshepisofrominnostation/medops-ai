"""Fixtures the browser must reproduce: semantic predictions, PHI screens, analytics.

Written from the Python service, consumed by scripts/check_app_parity.mjs. If the two
implementations ever disagree, that check fails — which is the only reason the page's
numbers can be trusted as the project's numbers rather than a lookalike.

    python scripts/make_app_fixtures.py [--out tests/data/app_parity.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import classifier as rule_engine                     # noqa: E402
from app import lifecycle, prioritizer                        # noqa: E402
from app.analytics import build_analytics                      # noqa: E402
from app.nlp import phi                                        # noqa: E402
from app.nlp.semantic import get_model                         # noqa: E402

# Deliberately awkward: terse messages, typos, a bilingual one, a message with no
# category vocabulary at all, and messages carrying patient data.
MESSAGES = [
    "The patient monitoring terminal in Bay 3 keeps disconnecting mid-surgery. This is unacceptable, we nearly lost a patient. Dr. S. Khumalo (Emergency Ward)",
    "Ventilator will not start in ICU, alarm screaming, patient on it now - Sr. Naidoo",
    "wifi down in the ward again",
    "cant log into the EMR system, password expired, need access urgently",
    "Theatre 2 aircon is blowing hot air, surgeons complaining",
    "Water leak in the corridor outside maternity, floor is flooding",
    "Please can you check why my payslip shows no overtime for October",
    "I want to apply for study leave for next year, forms please",
    "Invoice from MedSupply is double what we agreed, R48 000 instead of R24 000",
    "Urgent payment for the dialysis supplier, they are refusing delivery today",
    "Bathroom in ward 4B has no water since Monday",
    "Generator did not start during load shedding, theatre backup failed",
    "Roster for December is still not published, staff are threatening to strike",
    "Staff shortage in ICU tonight, short two nurses, no cover",
    "bed 12 patient Mr. Dlamini says his drip alarm keeps going off",
    "The 62-year-old woman in cubicle 7 has been waiting since Tuesday, she is on ARVs and her treatment was interrupted",
    "Patient tried to overdose last night, psychiatric referral needed, the lady from Germiston",
    "MRI scanner is offline, service provider says part is on backorder",
    "Kitchen fridge temperature log is not being completed, cold chain risk",
    "Elevator in block C is stuck between floors with people inside",
    "asdfgh qwerty zxcv",
    "Good morning, thank you for your help last week, could you please resend the tariff schedule",
    "Die rekenaar in ontvangs werk nie, ons kan nie pasiente help nie",
    "Security gate camera footage for the parking is not recording",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "tests" / "data" / "app_parity.json"))
    args = ap.parse_args()

    model = get_model()
    seed = json.loads((ROOT / "data" / "demo_tickets.json").read_text(encoding="utf-8"))

    predictions = []
    for text in MESSAGES:
        pred = model.predict(text)
        screen = phi.detect(text)
        rule_cat, rule_conf = rule_engine.classify(text)
        predictions.append({
            "text": text,
            # The routing the service actually uses, plus its priority rule.
            "rule_category": rule_cat,
            "rule_confidence": rule_conf,
            "priority": prioritizer.prioritize(text, ''),
            "category": pred["category"],
            "similarity": pred["similarity"],
            "margin": pred["margin"],
            "confident": pred["confident"],
            "scores": pred["scores"],
            "phi": {
                "blocked": screen["blocked"],
                "review": screen["review"],
                "rules": sorted({h["rule"] for h in screen["flags"]}),
            },
        })

    # Several windows, including one that is empty, so the JS must handle gaps too.
    windows = [
        {"start": None, "end": None},
        {"start": "2026-10-31", "end": "2026-11-06"},
        {"start": "2026-10-17", "end": "2026-10-23"},
        {"start": "2026-11-06", "end": "2026-11-06"},
        {"start": "2025-01-01", "end": "2025-01-07"},
    ]
    analytics = [
        {"start": w["start"], "end": w["end"],
         "value": build_analytics(seed, start=w["start"], end=w["end"])}
        for w in windows
    ]

    payload = {
        "generated_by": "scripts/make_app_fixtures.py",
        "ticket_count": len(seed),
        "sla_targets": dict(lifecycle.SLA_TARGET_MINUTES),
        "predictions": predictions,
        "analytics": analytics,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(predictions)} messages, {len(analytics)} windows, {len(seed)} tickets")


if __name__ == "__main__":
    main()
