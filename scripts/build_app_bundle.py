"""Export what the browser app needs from the Python service.

The Week 3 app runs on GitHub Pages, which cannot execute Python, so the semantic
classifier is shipped as data rather than re-implemented by eye: the IDF weights and
per-category centroids are computed here by the real `app.nlp.semantic` model and written
out. The browser only does the arithmetic it must (tokenise, project, cosine), and
`scripts/check_app_parity.mjs` proves it arrives at the same answers.

    python scripts/build_app_bundle.py [--out web/app_bundle.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import assigner, lifecycle                          # noqa: E402
from app import classifier as rule_engine                    # noqa: E402
from app import prioritizer                                  # noqa: E402
from app.analytics import CATEGORIES, PRIORITIES              # noqa: E402
from app.nlp import phi                                          # noqa: E402
from app.nlp.semantic import get_model, lexicon_priors, load_corpus  # noqa: E402


def build() -> dict:
    model = get_model()
    corpus = load_corpus()
    priors = lexicon_priors()
    return {
        "generated_from": "app.nlp.semantic.get_model()",
        "semantic": {
            # Rounded to 9 dp: far more precision than any cosine comparison needs,
            # and it keeps the bundle from ballooning with float repr noise.
            "idf": {k: round(v, 9) for k, v in model.idf.items()},
            "centroids": {
                label: {k: round(v, 9) for k, v in vec.items()}
                for label, vec in model.centroids.items()
            },
            "labels": model.labels,
            "trained_on": model.trained_on,
            "corpus_rows": len(corpus),
            "prior_rows": len(priors),
            # The gate the Python model uses to admit it does not know.
            "min_similarity": 0.12,
            "min_margin": 0.04,
            # Labelled sentences shown back to the user as "this is why": the same
            # corpus the model learned from, so the evidence is real.
            "corpus": [{"text": r["text"], "category": r["category"]} for r in corpus],
        },
        "phi": {
            # Shipped as data so the browser screen cannot drift from the service's.
            "patterns": [
                {"rule": name, "regex": rx, "severity": severity, "why": why,
                 # Honourific name rules are case-sensitive in the service on purpose.
                 "ignorecase": name not in ("named_person", "named_staff")}
                for name, rx, severity, why in phi.PATTERNS
            ],
            "not_names": sorted(phi.NOT_NAMES),
        },
        # The routing the service actually uses. The semantic model is the cross-check,
        # not the router: keyword weights carry domain knowledge the corpus cannot.
        "rules": {
            "category_keywords": {c: dict(k) for c, k in rule_engine.CATEGORY_KEYWORDS.items()},
            "default_category": rule_engine.DEFAULT_CATEGORY,
            "priority": {
                "clinical_context": prioritizer.CLINICAL_CONTEXT,
                "clinical_equipment": prioritizer.CLINICAL_EQUIPMENT,
                "safety": prioritizer.SAFETY,
                "urgent": prioritizer.URGENT,
                "staffing_critical": prioritizer.STAFFING_CRITICAL,
                "routine": prioritizer.ROUTINE
            },
            # Routing table straight from app/assigner.py, so the queue cannot drift.
            "assign": {
                cat: {prio: assigner.assign(cat, prio) for prio in ("High", "Medium", "Low")}
                for cat in rule_engine.CATEGORY_KEYWORDS
            }
        },
        "taxonomy": {
            "categories": list(CATEGORIES),
            "priorities": list(PRIORITIES),
            "statuses": list(lifecycle.STATUSES),
            "sla_targets_minutes": dict(lifecycle.SLA_TARGET_MINUTES),
        },
        "store": json.loads((ROOT / "data" / "demo_tickets.json").read_text(encoding="utf-8")),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "web" / "app_bundle.json"))
    args = ap.parse_args()
    bundle = build()
    Path(args.out).write_text(json.dumps(bundle, separators=(",", ":")), encoding="utf-8")
    size = Path(args.out).stat().st_size
    print(
        f"wrote {args.out} ({size / 1024:.0f} KB): "
        f"{bundle['semantic']['trained_on']} training docs, "
        f"{len(bundle['semantic']['idf'])} idf terms, "
        f"{len(bundle['store'])} seed tickets"
    )


if __name__ == "__main__":
    main()
