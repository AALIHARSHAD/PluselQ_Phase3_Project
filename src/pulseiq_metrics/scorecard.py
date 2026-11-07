"""Task 15 - executive scorecard: the eight KPIs, their targets and the traffic-light rule.

Every value comes from the metric view ``v_company_month`` (one row per month). This module only
decides *how to read* a value (target, direction, tolerance, status); it never queries raw tables.

Traffic-light rule (written down because kpi_targets gives targets but no thresholds):
    GREEN  value is on the good side of the target
    AMBER  value is on the bad side of the target, but within the tolerance below
    RED    value is outside the tolerance
    GREY   no target / reference exists for that month (never guessed)
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import pandas as pd

GREEN, AMBER, RED, GREY = "green", "amber", "red", "grey"
STATUS_WORD = {GREEN: "On target", AMBER: "Watch", RED: "Off target", GREY: "No target"}
STATUS_ICON = {GREEN: "●", AMBER: "▲", RED: "■", GREY: "○"}  # shape + word, so colour is never the only signal


@dataclass(frozen=True)
class KPI:
    key: str            # column in v_company_month
    metric_id: str      # id in the metric dictionary
    name: str           # name used in the metric dictionary
    unit: str           # "inr", "pct", "pct_pts"
    higher_is_better: bool
    target_col: str | None      # column holding the target / reference
    target_basis: str           # shown on the page
    tol_abs: float | None = None   # amber band in the KPI's own unit (percentage points or rupees)
    tol_rel: float | None = None   # amber band as a share of the target
    page: str = ""              # Streamlit page that explains the KPI
    why: str = ""               # one-sentence defence for the founder


KPIS: list[KPI] = [
    KPI("revenue", "M16", "Revenue", "inr", True, "revenue_ref", "provisional: average of previous 12 months (no target in kpi_targets)",
        tol_rel=0.10, page="p3/p11_pnl.py", why="Is the company earning? Everything else is paid out of it."),
    KPI("margin_pct", "M18", "Operating margin", "pct", True, "margin_ref", "provisional: average of previous 12 months (no target in kpi_targets)",
        tol_abs=3.0, page="p3/p11_pnl.py", why="Revenue that costs more than it brings in is not growth."),
    KPI("payroll_vs_budget_pct", "M09", "Payroll cost vs budget", "pct", False, None, "budget_payroll_dept_month: actual vs budget",
        tol_abs=2.0, page="p3/p13_dept.py", why="Payroll is the biggest cost (over 80% of expenses); an overspend moves profit at once."),
    KPI("overdue_receivables", "M21", "Overdue receivables", "inr", False, "overdue_ref", "provisional: average of previous 12 months (no target in kpi_targets)",
        tol_rel=0.10, page="p3/p12_cash.py", why="Profit is not cash. Money past its due date is the first sign of a cash squeeze."),
    KPI("attendance_pct", "M13", "Attendance rate", "pct", True, "attendance_target", "kpi_targets (headcount-weighted)",
        tol_abs=1.0, page="p3/p13_dept.py", why="Delivery capacity: people present on the days they are scheduled."),
    KPI("attrition_pct", "M04", "Attrition rate (monthly)", "pct", False, "attrition_target", "kpi_targets (headcount-weighted)",
        tol_abs=0.5, page="p3/p13_dept.py", why="Losing people costs hiring, ramp-up time and know-how."),
    KPI("overtime_share_pct", "M11", "Overtime share", "pct", False, "overtime_target", "kpi_targets (headcount-weighted)",
        tol_abs=0.5, page="p3/p13_dept.py", why="Early warning of overload, and of cost running outside plan."),
    KPI("task_completion_pct", "M22", "Task completion rate", "pct", True, "task_target", "kpi_targets (headcount-weighted)",
        tol_abs=5.0, page="p2_people.py", why="Are the teams actually finishing what they plan? The only delivery measure."),
]
KPI_BY_KEY = {k.key: k for k in KPIS}


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x) else float(x)


def target_for(kpi: KPI, row: pd.Series) -> float | None:
    """The number the KPI is judged against. Payroll is judged against 0% variance."""
    if kpi.key == "payroll_vs_budget_pct":
        return 0.0 if _num(row.get("budget_payroll")) is not None else None
    return _num(row.get(kpi.target_col)) if kpi.target_col else None


def status_for(kpi: KPI, value, target) -> str:
    value, target = _num(value), _num(target)
    if value is None or target is None:
        return GREY
    gap = (target - value) if kpi.higher_is_better else (value - target)   # > 0 means on the bad side
    if gap <= 0:
        return GREEN
    tol = kpi.tol_abs if kpi.tol_abs is not None else kpi.tol_rel * abs(target)
    return AMBER if gap <= tol else RED


def trend_is_good(kpi: KPI, delta) -> bool | None:
    d = _num(delta)
    if d is None or d == 0:
        return None
    return (d > 0) == kpi.higher_is_better


def build(company_month: pd.DataFrame, month, window: int = 12) -> list[dict]:
    """One dict per KPI for the chosen month: value, target, status, change vs previous month, trailing series."""
    cm = company_month.sort_values("month").reset_index(drop=True)
    month = pd.Timestamp(month)
    idx = cm.index[cm.month == month]
    if len(idx) != 1:
        raise ValueError(f"month {month:%Y-%m} not in v_company_month")
    i = int(idx[0])
    row, prev = cm.iloc[i], (cm.iloc[i - 1] if i else None)
    out = []
    for k in KPIS:
        v = _num(row[k.key]); t = target_for(k, row)
        pv = _num(prev[k.key]) if prev is not None else None
        out.append(dict(kpi=k, value=v, target=t, status=status_for(k, v, t),
                        delta=None if v is None or pv is None else v - pv, prev=pv,
                        series=cm[k.key].iloc[max(0, i - window + 1): i + 1].tolist(),
                        series_months=cm.month.iloc[max(0, i - window + 1): i + 1].tolist()))
    return out


def fmt_value(kpi: KPI, v) -> str:
    v = _num(v)
    if v is None:
        return "—"
    if kpi.unit == "inr":
        a = abs(v)
        return f"₹{a/1e7:,.2f} Cr" if a >= 1e7 else f"₹{a/1e5:,.1f} L"
    if kpi.key == "payroll_vs_budget_pct":
        return f"{v:+.1f}%"
    return f"{v:.1f}%" if kpi.key != "overtime_share_pct" else f"{v:.2f}%"


def fmt_target(kpi: KPI, t) -> str:
    t = _num(t)
    if t is None:
        return "—"
    if kpi.key == "payroll_vs_budget_pct":
        return "at or under budget"
    return ("≥ " if kpi.higher_is_better else "≤ ") + fmt_value(kpi, t)


def fmt_delta(kpi: KPI, d) -> str:
    d = _num(d)
    if d is None:
        return "—"
    if kpi.unit == "inr":
        return f"{'+' if d>=0 else '-'}{fmt_value(kpi, abs(d))}"
    return f"{d:+.2f} pts" if kpi.key == "overtime_share_pct" else f"{d:+.1f} pts"
