"""Week 5: the comparison must be honest about when it cannot tell methods apart."""
import datetime as dt
import random

from app.forecast_compare import compare_methods, MIN_DAYS


def _days(values, start="2026-01-05"):
    d0 = dt.date.fromisoformat(start)
    return [{"date": (d0 + dt.timedelta(days=i)).isoformat(), "count": v} for i, v in enumerate(values)]


def test_too_little_history_recommends_nothing():
    out = compare_methods(_days([3, 4, 5, 4, 3, 5]))
    assert out["comparable"] is False
    assert "no method is recommended" in out["verdict"].lower()
    assert out["methods"] == []


def test_exactly_at_threshold_is_comparable():
    out = compare_methods(_days([4] * MIN_DAYS))
    assert out["comparable"] is True


def test_strong_weekly_pattern_names_weekday_method_and_calls_it_real():
    # 12 weeks of a clean weekly cycle: weekdays busy, weekend near zero.
    week = [8, 9, 9, 8, 7, 1, 1]
    out = compare_methods(_days(week * 12))
    assert out["comparable"] is True
    assert out["best"] == "same weekday, all past weeks"
    assert out["distinguishable_from_luck"] is True
    assert "larger than chance" in out["verdict"]


def test_pure_noise_does_not_crown_a_winner():
    rng = random.Random(7)
    noise = [rng.randint(2, 8) for _ in range(28)]
    out = compare_methods(_days(noise))
    assert out["comparable"] is True
    assert out["distinguishable_from_luck"] is False
    assert "luck" in out["verdict"]


def test_interval_contains_the_point_estimate():
    rng = random.Random(3)
    out = compare_methods(_days([rng.randint(1, 9) for _ in range(30)]))
    lo, hi = out["interval_95"]
    assert lo <= out["advantage_tickets_per_day"] <= hi


def test_methods_are_ranked_best_first():
    out = compare_methods(_days([8, 9, 9, 8, 7, 1, 1] * 6))
    maes = [m["mae"] for m in out["methods"]]
    assert maes == sorted(maes)


def test_undated_rows_are_ignored_not_crashed_on():
    rows = _days([5] * 20) + [{"date": None, "count": 99}, {"count": 50}]
    out = compare_methods(rows)
    assert out["comparable"] is True
    assert out["days"] == 20


def test_deterministic_for_a_given_seed():
    rows = _days([3, 7, 2, 9, 4, 6, 1] * 4)
    assert compare_methods(rows, seed=5) == compare_methods(rows, seed=5)


def test_api_endpoint_returns_a_verdict():
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).get("/forecast/compare")
    assert r.status_code == 200
    body = r.json()
    assert "verdict" in body and "comparable" in body
