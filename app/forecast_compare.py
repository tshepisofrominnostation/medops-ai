"""Forecast method comparison (Week 5 hardening).

The Week 5 brief asks for "accurate analysis" and "insight explanation". On our own
21-day demo history the blended model is slightly WORSE than a flat 7-day average,
and a weekday-aware model is not reliably better either (its advantage is +0.07
tickets/day, with a 95% interval that comfortably crosses zero).

So instead of swapping the model and claiming an improvement, this module makes the
platform answer the question a manager actually has: "which method should I trust
here, and is the difference real or luck?" It will say "no method is distinguishable"
when that is the truth.

Walk-forward protocol: for each day t >= start, forecast day t using only days < t,
then score against the actual. No peeking.
"""
import datetime as dt
import random
import statistics as st
from typing import Callable, Dict, List, Optional

MIN_DAYS = 14          # below this a comparison is not worth publishing
MIN_EVAL_POINTS = 5    # below this the ranking is not stable
BOOTSTRAP_ROUNDS = 2000


def _flat_average(y: List[int], dates: List[dt.date], t: int) -> float:
    window = y[max(0, t - 7):t]
    return st.mean(window) if window else 0.0


def _weekday_mean(y: List[int], dates: List[dt.date], t: int) -> float:
    same = [y[i] for i in range(t) if dates[i].weekday() == dates[t].weekday()]
    return st.mean(same) if same else _flat_average(y, dates, t)


def _yesterday(y: List[int], dates: List[dt.date], t: int) -> float:
    return float(y[t - 1]) if t >= 1 else 0.0


METHODS: Dict[str, Callable] = {
    "flat 7-day average": _flat_average,
    "same weekday, all past weeks": _weekday_mean,
    "yesterday repeated": _yesterday,
}


def _series(by_day: List[dict]):
    rows = sorted((r for r in by_day if r.get("date")), key=lambda r: r["date"])
    dates = [dt.date.fromisoformat(r["date"]) for r in rows]
    y = [int(r.get("count", 0)) for r in rows]
    return y, dates


def compare_methods(by_day: List[dict], seed: int = 1) -> dict:
    """Score each method walk-forward and say whether the winner is real."""
    y, dates = _series(by_day)
    n = len(y)
    if n < MIN_DAYS:
        return {
            "comparable": False, "days": n,
            "verdict": (f"Only {n} days of history. A method comparison needs at least "
                        f"{MIN_DAYS}, so no method is recommended yet."),
            "methods": [],
        }

    start = max(7, n // 2)
    points = list(range(start, n))
    if len(points) < MIN_EVAL_POINTS:
        return {"comparable": False, "days": n,
                "verdict": "Too few held-out days to rank methods fairly.", "methods": []}

    errors: Dict[str, List[float]] = {}
    for name, fn in METHODS.items():
        errors[name] = [abs(round(fn(y, dates, t)) - y[t]) for t in points]

    ranked = sorted(
        ({"method": name, "mae": round(st.mean(e), 2)} for name, e in errors.items()),
        key=lambda r: r["mae"])
    best, runner = ranked[0]["method"], ranked[1]["method"]

    # Is the best method's advantage over the runner-up distinguishable from luck?
    diffs = [a - b for a, b in zip(errors[runner], errors[best])]
    rng = random.Random(seed)
    boots = sorted(st.mean(rng.choices(diffs, k=len(diffs))) for _ in range(BOOTSTRAP_ROUNDS))
    lo = boots[int(0.025 * BOOTSTRAP_ROUNDS)]
    hi = boots[int(0.975 * BOOTSTRAP_ROUNDS) - 1]
    mean_adv = st.mean(diffs)
    distinguishable = lo > 0

    if distinguishable:
        verdict = (f"'{best}' is the most accurate method here (average miss "
                   f"{ranked[0]['mae']} tickets/day) and its edge over '{runner}' is "
                   f"larger than chance would explain.")
    else:
        verdict = (f"'{best}' scored best ({ranked[0]['mae']} tickets/day average miss), "
                   f"but its edge over '{runner}' ({mean_adv:+.2f} tickets/day) is within "
                   f"what luck alone produces on {len(points)} test days. Treat the methods "
                   f"as equally good until there is more history.")

    return {
        "comparable": True, "days": n, "test_days": len(points),
        "methods": ranked,
        "best": best, "runner_up": runner,
        "advantage_tickets_per_day": round(mean_adv, 2),
        "interval_95": [round(lo, 2), round(hi, 2)],
        "distinguishable_from_luck": distinguishable,
        "verdict": verdict,
    }
