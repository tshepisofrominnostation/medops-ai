"""Inter-rater reliability for the evaluation set (S5-1).

R1 in docs/RISK_REPORT.md says our 20/20 score is an upper bound: one person wrote
the cases and the engine. A bigger score would not fix that. Measuring how much two
independent reviewers agree does, because it tells a reader how much of the score is
the system and how much is one person's judgement.

Usage:
    python3 scripts/eval_agreement.py reviewer_a.json reviewer_b.json

Each file: [{"case_id": "c1", "label": "pass"}, ...]
Labels are compared as strings, so any scheme works (pass/fail, 1-5, category names).
"""
import json
import sys
from typing import Dict, List, Tuple


def load(path: str) -> Dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a JSON list of {{case_id, label}} objects")
    out: Dict[str, str] = {}
    for row in rows:
        if "case_id" not in row or "label" not in row:
            raise ValueError(f"{path}: every row needs case_id and label")
        out[str(row["case_id"])] = str(row["label"])
    return out


def cohen_kappa(a: Dict[str, str], b: Dict[str, str]) -> Tuple[float, int, int]:
    """Return (kappa, agreed, compared) over the case_ids both reviewers labelled."""
    shared = sorted(set(a) & set(b))
    n = len(shared)
    if n == 0:
        raise ValueError("the two files share no case_id, so nothing can be compared")
    agree = sum(1 for k in shared if a[k] == b[k])
    po = agree / n
    labels = sorted({a[k] for k in shared} | {b[k] for k in shared})
    pe = sum((sum(1 for k in shared if a[k] == L) / n)
             * (sum(1 for k in shared if b[k] == L) / n) for L in labels)
    if pe >= 1.0:
        # Both reviewers used a single identical category: agreement is not informative.
        return (1.0 if po == 1.0 else 0.0), agree, n
    return (po - pe) / (1 - pe), agree, n


def band(kappa: float) -> str:
    """Plain-language reading (Landis & Koch bands, rounded for humans)."""
    if kappa >= 0.8:
        return "good - the reviewers largely agree; the score is reproducible"
    if kappa >= 0.6:
        return "fair - useful, but borderline cases are being judged differently"
    if kappa >= 0.4:
        return "weak - disagreement is large enough to change the headline score"
    return "poor - the labels are closer to chance than to a shared standard"


def summarise(path_a: str, path_b: str) -> dict:
    a, b = load(path_a), load(path_b)
    kappa, agree, n = cohen_kappa(a, b)
    only_a = len(set(a) - set(b))
    only_b = len(set(b) - set(a))
    return {
        "compared": n, "agreed": agree, "percent_agreement": round(100 * agree / n, 1),
        "kappa": round(kappa, 3), "verdict": band(kappa),
        "unmatched": {"only_in_a": only_a, "only_in_b": only_b},
    }


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip())
        return 2
    try:
        result = summarise(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"compared {result['compared']} cases")
    print(f"agreement {result['percent_agreement']}%  kappa {result['kappa']}")
    print(f"verdict   {result['verdict']}")
    if result["unmatched"]["only_in_a"] or result["unmatched"]["only_in_b"]:
        print(f"unmatched cases: {result['unmatched']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
