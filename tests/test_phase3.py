"""Phase 3 tests: every headline number ties to the README answer key / reference summary, and the scorecard rules behave."""
import math
import pandas as pd
import pytest

from pulseiq_metrics.views import Warehouse, OPEN_STATUSES
from pulseiq_metrics import scorecard as sc


@pytest.fixture(scope="module")
def w():
    return Warehouse()


@pytest.fixture(scope="module")
def key(w):
    k = w.tables["reconciliation_answer_key"].copy()
    k["period"] = k.month.dt.strftime("%Y-%m")
    return k


# ------------------------------------------------------------------ Task 11
def test_group_accounts_not_in_detail_view(w):
    groups = set(w.tables["dim_account"].query("is_group == 'Y'").account_code)
    used = set(w.view("v_pl_account_month").account_code)
    assert groups.isdisjoint(used)


def test_pl_ties_to_readme_except_known_dq04(w, key):
    m = w.view("v_pl_monthly").merge(key, on="period")
    assert ((m.revenue - m.ledger_revenue).abs() < 0.01).all()
    bad = m[(m.expense - m.ledger_total_expense).abs() > 0.01]
    assert list(bad.period) == ["2026-06"]                       # DQ-04, planted
    assert abs((bad.expense - bad.ledger_total_expense).iloc[0] - 18450) < 0.01
    ok = m[m.period != "2026-06"]
    assert ((ok.net_profit - ok.ledger_net_profit).abs() < 0.01).all()


def test_margin_is_profit_over_revenue(w):
    m = w.view("v_pl_monthly")
    assert ((m.margin_pct - 100 * m.net_profit / m.revenue).abs() < 1e-9).all()


def test_vendor_view_has_no_duplicate_bills(w):
    v = w.view("v_vendor_spend")
    assert v.expense_id.is_unique


# ------------------------------------------------------------------ Task 12
def test_ageing_buckets_add_up_to_open_receivables_and_readme(w, key):
    ar, ag = w.view("v_ar_open"), w.view("v_ar_ageing")
    assert abs(ag.balance.sum() - ar.balance_due.sum()) < 0.01
    assert abs(ar.balance_due.sum() - key.receivables_closing_balance.iloc[-1]) < 0.01


def test_only_open_statuses_in_ar(w):
    assert set(w.view("v_ar_open").status) <= set(OPEN_STATUSES)


def test_receivables_history_matches_readme_every_month(w, key):
    m = w.view("v_ar_month_end").merge(key, on="period")
    assert len(m) == 18 and ((m.receivables_closing - m.receivables_closing_balance).abs() < 1).all()


def test_bank_balance_rebuilds_readme(w, key):
    cm = w.view("v_cash_monthly"); cm = cm[cm.source_type != "OPENING"]
    opening = w.tables["fact_ledger"].query("account_code=='1001' and source_type=='OPENING'").debit.sum()
    mm = cm.groupby("period")[["cash_in", "cash_out"]].sum()
    closing = (opening + (mm.cash_in - mm.cash_out).cumsum()).reset_index(name="c").merge(key, on="period")
    assert ((closing.c - closing.bank_closing_balance).abs() < 1).all()


# ------------------------------------------------------------------ Task 13
def test_dept_month_grain_and_reference(w):
    dm, ref = w.view("v_dept_month"), w.tables["reference_summary_dept_month"]
    assert not dm.duplicated(["department_id", "month"]).any()
    j = dm.merge(ref, on=["department_id", "month"], suffixes=("", "_r"))
    assert len(j) == len(ref) == len(dm)
    for c in ("employer_cost", "gross_pay", "overtime_pay"):
        assert ((j[c] - j[c + "_r"]).abs() < 0.01).all(), c
    for c in ("employees_paid", "overtime_hours", "late_arrivals", "headcount_end", "hires", "exits"):
        assert (j[c] == j[c + "_r"]).all(), c


def test_join_does_not_inflate_payroll(w):
    assert abs(w.view("v_dept_month").employer_cost.sum() - w.tables["fact_payroll"].employer_cost.sum()) < 0.01


# ------------------------------------------------------------------ Task 14
def test_anomaly_money_blank_for_attendance(w):
    a = w.view("v_anomaly_type")
    assert a[a.source_dataset.str.startswith("attendance")].money_at_risk.isna().all()


def test_backtest_replicates_stored_forecast():
    from pulseiq_metrics.forecast import baseline, company_series
    t = Warehouse().tables
    s = company_series(t)["headcount_end"]
    fc = t["fact_forecast"].query("metric=='headcount_end' and department_id=='ALL'").sort_values("forecast_month")
    mine = baseline(s)
    assert (mine.forecast.values - fc.forecast_value.values).__abs__().max() < 0.5


# ------------------------------------------------------------------ Task 15
def test_scorecard_has_eight_kpis_with_metric_ids():
    assert len(sc.KPIS) == 8
    assert all(k.metric_id.startswith("M") for k in sc.KPIS)


def test_status_rules():
    att = sc.KPI_BY_KEY["attendance_pct"]          # higher better, amber band 1.0 pt
    assert sc.status_for(att, 94.0, 94.0) == sc.GREEN
    assert sc.status_for(att, 93.2, 94.0) == sc.AMBER
    assert sc.status_for(att, 92.9, 94.0) == sc.RED
    attr = sc.KPI_BY_KEY["attrition_pct"]          # lower better, amber band 0.5 pt
    assert sc.status_for(attr, 1.0, 1.0) == sc.GREEN
    assert sc.status_for(attr, 1.4, 1.0) == sc.AMBER
    assert sc.status_for(attr, 1.6, 1.0) == sc.RED
    assert sc.status_for(attr, None, 1.0) == sc.GREY and sc.status_for(attr, 1.0, math.nan) == sc.GREY


def test_scorecard_uses_only_the_metric_view(w):
    cm = w.view("v_company_month")
    assert set(k.key for k in sc.KPIS) <= set(cm.columns)
    rows = sc.build(cm, cm.month.max())
    assert len(rows) == 8 and all(r["value"] is not None for r in rows)


def test_scorecard_ties_to_detail_pages(w, key):
    cm = w.view("v_company_month"); last = cm.month.max()
    r = {x["kpi"].key: x for x in sc.build(cm, last)}
    pl = w.view("v_pl_monthly").iloc[-1]
    assert abs(r["revenue"]["value"] - pl.revenue) < 0.01
    assert abs(r["margin_pct"]["value"] - pl.margin_pct) < 1e-9
    assert abs(r["overdue_receivables"]["value"] - w.view("v_ar_open").query("days_past_due>0").balance_due.sum()) < 0.01
    dm = w.view("v_dept_month"); dm = dm[dm.month == last]
    assert abs(r["payroll_vs_budget_pct"]["value"] - 100 * (dm.employer_cost.sum() / cm.budget_payroll.iloc[-1] - 1)) < 1e-6


def test_first_month_has_no_provisional_reference(w):
    cm = w.view("v_company_month")
    first = {x["kpi"].key: x for x in sc.build(cm, cm.month.min())}
    assert first["revenue"]["status"] == sc.GREY and first["attendance_pct"]["status"] != sc.GREY
