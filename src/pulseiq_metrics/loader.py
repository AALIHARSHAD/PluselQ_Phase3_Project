"""Load the master workbook once, cache each sheet as parquet, clean the facts.

Cleaning rules are the same ones documented in docs/decisions.md (Task 1) and
dq_checks_catalog; every rule returns what it removed so pages can show it.
"""
from __future__ import annotations
import os
from pathlib import Path
import pandas as pd

ROOT = Path(os.environ.get("PULSEIQ_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
WORKBOOK = DATA_DIR / "PulseIQ_master_dataset.xlsx"
CACHE = DATA_DIR / "warehouse"

SHEETS = [
    "dim_account", "dim_department", "dim_employee", "dim_client", "dim_vendor",
    "fact_ledger", "fact_expense", "fact_invoice", "fact_invoice_payment",
    "fact_payroll", "fact_attendance_monthly", "fact_leave", "fact_headcount_monthly",
    "fact_task", "fact_anomaly", "fact_forecast", "fact_attrition_risk",
    "kpi_targets", "budget_payroll_dept_month", "reconciliation_answer_key",
    "reference_summary_dept_month", "dq_known_issues", "metric_dictionary",
]
CUTOFF = pd.Timestamp("2026-09-30")  # README: cut-off 30 Sep 2026


def _read(name: str) -> pd.DataFrame:
    p = CACHE / f"{name}.parquet"
    if p.exists() and (not WORKBOOK.exists() or p.stat().st_mtime >= WORKBOOK.stat().st_mtime):
        return pd.read_parquet(p)
    if not WORKBOOK.exists():
        raise FileNotFoundError(f"Master workbook not found: {WORKBOOK}")
    df = pd.read_excel(WORKBOOK, sheet_name=name)
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return df


def load_raw() -> dict[str, pd.DataFrame]:
    return {s: _read(s) for s in SHEETS}


def clean(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return (clean tables, log of removed/fixed rows)."""
    t = {k: v.copy() for k, v in raw.items()}
    log = []

    acc = t["dim_account"]; acc["account_code"] = acc["account_code"].astype(str)
    acc["parent_code"] = acc["parent_code"].astype("Int64").astype(str).replace("<NA>", None)
    led = t["fact_ledger"]; led["account_code"] = led["account_code"].astype(str)
    for c in ("service_line_account",):
        t["fact_invoice"][c] = t["fact_invoice"][c].astype(str)
    t["fact_expense"]["category_account"] = t["fact_expense"]["category_account"].astype(str)
    t["dim_vendor"]["primary_expense_account"] = t["dim_vendor"]["primary_expense_account"].astype(str)

    emp = t["dim_employee"]
    cur = emp[emp.is_current == "Y"].drop_duplicates("employee_id").set_index("employee_id")
    known = set(emp.employee_id)

    # payroll: orphans + duplicates (DQ-C03, DQ-C04)
    p = t["fact_payroll"]
    orphan = ~p.employee_id.isin(known)
    log += [("fact_payroll", r.payroll_item_id, "ORPHAN_FOREIGN_KEY") for r in p[orphan].itertuples()]
    p = p[~orphan].sort_values("payroll_item_id")
    dup = p.duplicated(["employee_id", "run_id"], keep="first")
    log += [("fact_payroll", r.payroll_item_id, "DUPLICATE_PAYROLL_ROW") for r in p[dup].itertuples()]
    p = p[~dup].copy()
    p["month"] = pd.to_datetime(p.period_end_date).dt.to_period("M").dt.to_timestamp()
    t["fact_payroll"] = p

    # attendance after exit month (DQ-C05)
    a = t["fact_attendance_monthly"].copy()
    a["period_end_date"] = pd.to_datetime(a.period_end_date)
    ex = a.employee_id.map(cur.exit_date)
    bad = ex.notna() & (a.period_end_date > (pd.to_datetime(ex) + pd.offsets.MonthEnd(0)))
    log += [("fact_attendance_monthly", r.attendance_fact_id, "ATTENDANCE_AFTER_EXIT") for r in a[bad].itertuples()]
    a = a[~bad].copy()
    a["month"] = a.period_end_date.dt.to_period("M").dt.to_timestamp()
    t["fact_attendance_monthly"] = a

    # leave: swap reversed dates (DQ-C10), keep the fix visible
    l = t["fact_leave"].copy()
    l["start_date"] = pd.to_datetime(l.start_date); l["end_date"] = pd.to_datetime(l.end_date)
    sw = l.end_date < l.start_date
    log += [("fact_leave", r.leave_request_id, "END_BEFORE_START_swapped") for r in l[sw].itertuples()]
    l.loc[sw, ["start_date", "end_date"]] = l.loc[sw, ["end_date", "start_date"]].values
    l["month"] = l.start_date.dt.to_period("M").dt.to_timestamp()
    t["fact_leave"] = l

    # attrition risk: stale predictions (DQ-C11)
    r = t["fact_attrition_risk"].copy(); r["as_of_date"] = pd.to_datetime(r.as_of_date)
    stale = r.as_of_date < r.as_of_date.max() - pd.Timedelta(days=7)
    log += [("fact_attrition_risk", x.prediction_id, "STALE_PREDICTION") for x in r[stale].itertuples()]
    t["fact_attrition_risk"] = r[~stale].copy()

    for k in ("fact_expense", "fact_invoice", "fact_invoice_payment"):
        for c in t[k].columns:
            if c.endswith("_date") or c == "invoice_date":
                t[k][c] = pd.to_datetime(t[k][c], errors="coerce")
    for k, c in (("fact_headcount_monthly", "month_start_date"), ("kpi_targets", "month"),
                 ("budget_payroll_dept_month", "month"), ("reference_summary_dept_month", "month"),
                 ("reconciliation_answer_key", "month"), ("fact_forecast", "forecast_month")):
        t[k][c] = pd.to_datetime(t[k][c])
    t["fact_headcount_monthly"]["month"] = t["fact_headcount_monthly"].month_start_date
    t["fact_anomaly"]["period"] = pd.to_datetime(t["fact_anomaly"].period)
    return t, pd.DataFrame(log, columns=["table", "record_id", "rule"])


def load_clean():
    return clean(load_raw())
