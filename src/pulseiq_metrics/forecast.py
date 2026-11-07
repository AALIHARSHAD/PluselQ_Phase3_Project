"""Back-test of the AI team's baseline forecast method.

fact_forecast was trained through 2026-09 = the last month of actuals, so no stored
forecast month has an actual yet. To measure error honestly we re-run the documented
method ("linear trend (36m) + half-strength seasonality") from earlier origins and
compare with actuals that were already known. The point forecast replicates the stored
Oct-2026 to Mar-2027 values exactly; the 80% band is approximated (z=1.2816 x residual sd
x sqrt(1+0.28h), fitted to the stored band), so coverage is indicative only.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

Z80 = 1.2816


def company_series(t: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    h = t["fact_headcount_monthly"]
    g = h.groupby("month").agg(he=("headcount_end", "sum"), ex=("exits", "sum"), hs=("headcount_start", "sum"))
    return {"headcount_end": g.he.sort_index(), "attrition_rate_monthly_pct": (100 * g.ex / g.hs).sort_index()}


def baseline(s: pd.Series, horizon: int = 6, n: int = 36, w: float = 0.5) -> pd.DataFrame:
    y = s.iloc[-n:]
    x = np.arange(n)
    b, a = np.polyfit(x, y.values, 1)
    res = y.values - (a + b * x)
    seas = pd.Series(res, index=y.index.month).groupby(level=0).mean()
    sd = res.std(ddof=2)
    rows = []
    for k in range(1, horizon + 1):
        m = y.index[-1] + pd.offsets.MonthBegin(k)
        v = a + b * (n - 1 + k) + w * seas.get(m.month, 0.0)
        half = Z80 * sd * np.sqrt(1 + 0.28 * k)
        rows.append((m, k, v, v - half, v + half))
    return pd.DataFrame(rows, columns=["month", "horizon", "forecast", "lower_80", "upper_80"])


def backtest(s: pd.Series, horizon: int = 6, min_history: int = 36) -> pd.DataFrame:
    out = []
    for i in range(min_history, len(s)):
        train = s.iloc[:i]
        fc = baseline(train, horizon)
        for r in fc.itertuples():
            if r.month in s.index:
                a = s[r.month]
                out.append(dict(origin=train.index[-1], month=r.month, horizon=r.horizon, actual=a,
                                forecast=r.forecast, lower_80=r.lower_80, upper_80=r.upper_80,
                                naive=train.iloc[-1]))
    d = pd.DataFrame(out)
    d["ape"] = 100 * (d.actual - d.forecast).abs() / d.actual
    d["naive_ape"] = 100 * (d.actual - d.naive).abs() / d.actual
    d["in_band"] = (d.actual >= d.lower_80) & (d.actual <= d.upper_80)
    return d


def error_by_horizon(bt: pd.DataFrame) -> pd.DataFrame:
    return bt.groupby("horizon").agg(forecasts=("ape", "size"), mape_pct=("ape", "mean"),
                                     naive_mape_pct=("naive_ape", "mean"),
                                     band_coverage_pct=("in_band", lambda x: 100 * x.mean())).reset_index()
