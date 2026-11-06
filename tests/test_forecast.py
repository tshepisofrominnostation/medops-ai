"""S3-1: the forecast must be honest - horizon correct, error measured, no trend invented."""
from app.forecast import forecast_volume, forecast_from_analytics


def _hist(counts, start_day=1):
    return [{"date": f"2026-11-{start_day + i:02d}", "count": c} for i, c in enumerate(counts)]


def test_forecast_returns_requested_horizon():
    out = forecast_volume(_hist([3, 4, 5, 6, 7, 8, 9, 10]), horizon=5)
    assert len(out["forecast"]) == 5
    assert out["predicted_total"] == sum(f["predicted"] for f in out["forecast"])
    assert all(f["predicted"] >= 0 for f in out["forecast"])


def test_rising_series_produces_rising_forecast_and_positive_slope():
    out = forecast_volume(_hist([2, 3, 4, 5, 6, 7, 8, 9, 10]), horizon=3)
    assert out["slope_per_day"] > 0
    vals = [f["predicted"] for f in out["forecast"]]
    assert vals == sorted(vals), vals


def test_backtest_error_is_reported_when_enough_history():
    out = forecast_volume(_hist([4, 5, 4, 6, 5, 7, 6, 8, 7, 9]), horizon=2)
    assert out["backtest_mae"] is not None and out["backtest_mae"] >= 0
    assert out["reliable"] is True


def test_short_history_is_flagged_unreliable_not_padded():
    out = forecast_volume(_hist([5, 6]), horizon=3)
    assert out["reliable"] is False
    assert out["backtest_mae"] is None


def test_empty_history_returns_zero_forecast():
    out = forecast_volume([], horizon=4)
    assert out["predicted_total"] == 0 and out["forecast"] == []
    assert out["reliable"] is False


def test_wrapper_accepts_analytics_payload():
    payload = {"by_day": _hist([3, 3, 3, 3, 3, 3])}
    out = forecast_from_analytics(payload, horizon=3)
    # flat history -> forecast should sit near the flat level, not drift
    assert all(abs(f["predicted"] - 3) <= 1 for f in out["forecast"])
