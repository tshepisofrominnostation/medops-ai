"""Ticket surge forecast v1 (S3-1).

A deliberately simple model: a 7-day moving average combined with a linear trend
fitted on daily ticket counts. The point of this module is not sophistication, it
is honesty - every forecast ships with a backtested error so a manager knows how
much to trust it.

Backtest protocol: fit on the first 70% of the history, predict the remainder,
report mean absolute error (MAE) on the held-out tail. No peeking.
"""
from datetime import date, timedelta
from typing import Optional


def _series(by_day: list[dict], history_days: Optional[int] = None) -> list[int]:
    """Daily counts, oldest first, optionally limited to the most recent N days."""
    counts = [int(d["count"]) for d in sorted(by_day, key=lambda d: d["date"])]
    if history_days and history_days > 0:
        counts = counts[-history_days:]
    return counts


def _linfit(y: list[float]) -> tuple[float, float]:
    """Least-squares fit of y against x = 0..n-1. Returns (intercept, slope)."""
    n = len(y)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return float(y[0]), 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(y) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(y))
    den = sum((i - mean_x) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    return mean_y - slope * mean_x, slope


def _ma(values: list[int], window: int) -> float:
    if not values:
        return 0.0
    tail = values[-window:]
    return sum(tail) / len(tail)


def forecast_volume(by_day: list[dict], horizon: int = 7,
                    history_days: Optional[int] = None) -> dict:
    """Forecast the next `horizon` days of ticket volume.

    Returns the forecast, the method used, and a backtested MAE. If there is not
    enough history the model falls back to the moving average alone and says so
    via ``reliable: false`` - it never pretends to a trend it cannot fit.
    """
    history = _series(by_day, history_days)
    if not history:
        return {
            "method": "none", "horizon": horizon, "history_days": 0,
            "reliable": False, "backtest_mae": None, "predicted_total": 0,
            "forecast": [],
        }

    # backtest on the tail: fit on the first 70%, score on the last 30%
    split = max(2, int(len(history) * 0.7))
    backtest_mae = None
    if len(history) - split >= 2:
        a, b = _linfit(history[:split])
        errs = [abs((a + b * (split + i)) - history[split + i])
                for i in range(len(history) - split)]
        backtest_mae = round(sum(errs) / len(errs), 2)

    intercept, slope = _linfit(history)
    ma = _ma(history, min(7, len(history)))
    reliable = len(history) >= 5

    # blend the trend line with the short moving average: the average damps spikes,
    # the trend captures direction. 50/50, stated plainly rather than tuned away.
    last_day = None
    if by_day:
        days = sorted(d["date"] for d in by_day)
        last_day = days[-1]
    try:
        start = date.fromisoformat(last_day) if last_day else date.today()
    except ValueError:
        start = date.today()

    forecast = []
    for step in range(horizon):
        trend = intercept + slope * (len(history) - 1 + step)
        blended = 0.5 * trend + 0.5 * ma
        value = max(0, round(blended))
        forecast.append({
            "date": (start + timedelta(days=step + 1)).isoformat(),
            "predicted": value,
        })

    return {
        "method": "moving_average_7 + linear_trend (50/50 blend)",
        "horizon": horizon,
        "history_days": len(history),
        "reliable": reliable,
        "slope_per_day": round(slope, 3),
        "recent_daily_average": round(ma, 2),
        "backtest_mae": backtest_mae,
        "predicted_total": sum(f["predicted"] for f in forecast),
        "forecast": forecast,
    }


def forecast_from_analytics(analytics: dict, horizon: int = 7) -> dict:
    """Convenience wrapper: forecast straight from an /analytics payload."""
    return forecast_volume(analytics.get("by_day", []), horizon=horizon)
