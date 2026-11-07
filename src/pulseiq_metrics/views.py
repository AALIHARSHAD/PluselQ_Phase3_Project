"""Metric views (DuckDB). Every dashboard number comes from one of these views.

Naming: v_<subject>_<grain>. Each view lists the metric IDs it serves
(see docs/metric_dictionary.md) so a number can be traced back to its source.
"""
from __future__ import annotations
import duckdb
import pandas as pd
from .loader import load_clean, CUTOFF

OPEN_STATUSES = ("SENT", "OVERDUE", "PARTIALLY_PAID")
MIN_GROUP = 5  # metric_dictionary minimum group size / DQ-C14

VIEWS: dict[str, str] = {}

# ---------------------------------------------------------------- Task 11
# Group accounts (is_group='Y') are headings: never summed, so a parent and its children are never double counted.
VIEWS["v_ledger_detail"] = """
SELECT l.*, a.account_name, a.account_type, a.parent_code
FROM fact_ledger l JOIN dim_account a USING (account_code)
WHERE a.is_group = 'N'"""

VIEWS["v_pl_account_month"] = """  -- M16, M17
SELECT posting_period AS period, account_code, account_name, account_type,
       SUM(CASE WHEN account_type='INCOME' THEN credit-debit ELSE debit-credit END) AS amount
FROM v_ledger_detail WHERE account_type IN ('INCOME','EXPENSE')
GROUP BY ALL"""

VIEWS["v_pl_monthly"] = """  -- M16 revenue, M17 net profit, M18 margin
SELECT period,
       SUM(amount) FILTER (account_type='INCOME')  AS revenue,
       SUM(amount) FILTER (account_type='EXPENSE') AS expense,
       SUM(amount) FILTER (account_type='INCOME') - SUM(amount) FILTER (account_type='EXPENSE') AS net_profit,
       100*(SUM(amount) FILTER (account_type='INCOME') - SUM(amount) FILTER (account_type='EXPENSE'))
          / SUM(amount) FILTER (account_type='INCOME') AS margin_pct
FROM v_pl_account_month GROUP BY period ORDER BY period"""

VIEWS["v_expense_category_month"] = """
SELECT period, account_code, account_name AS category, amount
FROM v_pl_account_month WHERE account_type='EXPENSE'"""

VIEWS["v_vendor_spend"] = """  -- bills before GST (what the ledger books as expense); cancelled/none present
SELECT e.vendor_id, v.vendor_name, e.category_account, strftime(e.expense_date,'%Y-%m') AS period,
       e.amount_excl_gst AS amount, e.total_amount, e.status, e.expense_id
FROM fact_expense e LEFT JOIN dim_vendor v USING (vendor_id)"""

VIEWS["v_payroll_ledger_check"] = """  -- DQ-C01: payroll employer cost vs ledger 5001-5005
SELECT l.period, p.cost AS payroll_cost, l.exp AS ledger_salary_expense, l.exp - p.cost AS diff
FROM (SELECT period, SUM(amount) exp FROM v_pl_account_month
      WHERE account_code IN ('5001','5002','5003','5004','5005') GROUP BY period) l
JOIN (SELECT strftime(month,'%Y-%m') period, SUM(employer_cost) cost FROM fact_payroll GROUP BY 1) p USING (period)"""

# ---------------------------------------------------------------- Task 12
VIEWS["v_ar_open"] = f"""  -- M21: open = SENT, OVERDUE, PARTIALLY_PAID. DRAFT and CANCELLED are not receivables.
SELECT i.invoice_id, i.client_id, c.client_name, i.invoice_date, i.due_date, i.status, i.balance_due,
       GREATEST(date_diff('day', i.due_date, DATE '{CUTOFF.date()}'), 0) AS days_past_due,
       date_diff('day', i.invoice_date, DATE '{CUTOFF.date()}') AS invoice_age_days,
       CASE WHEN i.due_date >= DATE '{CUTOFF.date()}' THEN 'Not yet due'
            WHEN date_diff('day', i.due_date, DATE '{CUTOFF.date()}') <= 30 THEN '0-30'
            WHEN date_diff('day', i.due_date, DATE '{CUTOFF.date()}') <= 60 THEN '31-60'
            WHEN date_diff('day', i.due_date, DATE '{CUTOFF.date()}') <= 90 THEN '61-90'
            ELSE '90+' END AS bucket
FROM fact_invoice i JOIN dim_client c USING (client_id)
WHERE i.status IN {OPEN_STATUSES}"""

VIEWS["v_ar_ageing"] = """
SELECT bucket, COUNT(*) AS invoices, SUM(balance_due) AS balance FROM v_ar_open GROUP BY bucket"""

VIEWS["v_days_to_pay_client"] = """  -- paid invoices only; days = last payment date - invoice date
WITH last_pay AS (SELECT invoice_id, MAX(payment_date) AS paid_on FROM fact_invoice_payment GROUP BY 1),
paid AS (SELECT i.client_id, i.invoice_id, i.total_amount, i.invoice_date, i.due_date, lp.paid_on,
                date_diff('day', i.invoice_date, lp.paid_on) AS days_to_pay,
                date_diff('day', i.due_date, lp.paid_on)     AS days_late
         FROM fact_invoice i JOIN last_pay lp USING (invoice_id) WHERE i.status='PAID')
SELECT c.client_id, c.client_name, c.payment_terms_days, c.payment_behaviour,
       COUNT(*) AS paid_invoices, AVG(days_to_pay) AS avg_days_to_pay,
       SUM(days_to_pay*total_amount)/SUM(total_amount) AS weighted_days_to_pay,
       MAX(days_to_pay) AS max_days_to_pay, AVG(days_late) AS avg_days_late
FROM paid p JOIN dim_client c USING (client_id) GROUP BY ALL"""

VIEWS["v_overdue_client"] = """  -- M21 by client
SELECT client_id, client_name, SUM(balance_due) FILTER (days_past_due>0) AS overdue_balance,
       SUM(balance_due) AS open_balance, MAX(days_past_due) AS oldest_days_past_due,
       COUNT(*) FILTER (days_past_due>0) AS overdue_invoices
FROM v_ar_open GROUP BY 1,2"""

VIEWS["v_cash_monthly"] = """  -- bank account 1001 movements, from the ledger
SELECT posting_period AS period, source_type,
       SUM(debit) AS cash_in, SUM(credit) AS cash_out, SUM(debit-credit) AS net
FROM fact_ledger WHERE account_code='1001' GROUP BY ALL"""

# ---------------------------------------------------------------- Task 13
VIEWS["v_payroll_dm"] = """
SELECT department_id, month, SUM(employer_cost) employer_cost, SUM(gross_pay) gross_pay,
       SUM(overtime_pay) overtime_pay, COUNT(DISTINCT employee_id) employees_paid
FROM fact_payroll GROUP BY 1,2"""
VIEWS["v_attendance_dm"] = """
SELECT department_id, month, SUM(scheduled_days) scheduled_days, SUM(present_days) present_days,
       SUM(half_days_unpaid) half_days_unpaid, SUM(late_arrivals) late_arrivals, SUM(overtime_hours) overtime_hours
FROM fact_attendance_monthly GROUP BY 1,2"""
VIEWS["v_headcount_dm"] = """
SELECT department_id, month, headcount_start, hires, exits, voluntary_exits, headcount_end,
       attrition_rate_monthly_pct FROM fact_headcount_monthly"""
VIEWS["v_leave_dm"] = """  -- approved leave days, allocated to the start month; department from the employee version in the fact
SELECT e.department_id, l.month, SUM(l.days) leave_days
FROM fact_leave l JOIN dim_employee e USING (employee_key)
WHERE l.status='Approved' GROUP BY 1,2"""

VIEWS["v_dept_month"] = """  -- grain: department x month. Each source is aggregated first, then joined (M09, M10, M11, M13, M04)
SELECT p.department_id, d.department_name, p.month,
       p.employer_cost, p.gross_pay, p.overtime_pay, p.employees_paid,
       a.overtime_hours, a.late_arrivals,
       (a.present_days + 0.5*a.half_days_unpaid)/NULLIF(a.scheduled_days,0) AS attendance_rate,
       h.headcount_end, h.hires, h.exits, h.attrition_rate_monthly_pct,
       COALESCE(lv.leave_days,0) AS leave_days,
       COALESCE(lv.leave_days,0)/NULLIF(p.employees_paid,0) AS leave_days_per_head,
       p.employer_cost/NULLIF(p.employees_paid,0) AS cost_per_head,
       100*p.overtime_pay/NULLIF(p.employer_cost,0) AS overtime_share_pct
FROM v_payroll_dm p
LEFT JOIN v_attendance_dm a USING (department_id, month)
LEFT JOIN v_headcount_dm h USING (department_id, month)
LEFT JOIN v_leave_dm lv USING (department_id, month)
LEFT JOIN dim_department d USING (department_id)"""

# ---------------------------------------------------------------- Task 14
VIEWS["v_anomaly_type"] = """  -- M26; money_at_risk is blank by contract for attendance rows
SELECT source_dataset, reason_code, ANY_VALUE(reason_text) AS reason_text, COUNT(*) AS n_flags,
       SUM(money_at_risk) AS money_at_risk, AVG(anomaly_score) AS avg_score
FROM fact_anomaly WHERE flagged='Y' GROUP BY 1,2"""

# ---------------------------------------------------------------- Task 15
VIEWS["v_overdue_month_end"] = f"""  -- M21 / M20 helper: current overdue + DSO at cut-off
SELECT SUM(balance_due) FILTER (days_past_due>0) AS overdue_receivables, SUM(balance_due) AS open_receivables FROM v_ar_open"""


VIEWS["v_ar_month_end"] = """  -- receivables at each month end, rebuilt from invoices and payments (M20/M21 history)
WITH me AS (SELECT DISTINCT last_day(CAST(period||'-01' AS DATE)) AS month_end, period FROM v_pl_monthly),
pay AS (SELECT invoice_id, payment_date, amount FROM fact_invoice_payment),
inv AS (SELECT * FROM fact_invoice WHERE status NOT IN ('DRAFT','CANCELLED')),
bal AS (
  SELECT me.period, me.month_end, i.invoice_id, i.due_date,
         i.total_amount - COALESCE((SELECT SUM(p.amount) FROM pay p WHERE p.invoice_id=i.invoice_id
                                    AND p.payment_date <= me.month_end),0) AS balance
  FROM me JOIN inv i ON i.invoice_date <= me.month_end)
SELECT period, SUM(balance) AS receivables_closing,
       SUM(balance) FILTER (due_date < month_end) AS overdue_receivables
FROM bal WHERE balance <> 0 GROUP BY period ORDER BY period"""


VIEWS["v_company_month"] = """  -- one row per month: the eight scorecard KPIs (M16, M18, M09 vs budget, M21, M13, M04, M11, M22) + context
WITH pl AS (SELECT CAST(period||'-01' AS DATE) AS month, period, revenue, margin_pct FROM v_pl_monthly),
pay AS (SELECT month, SUM(employer_cost) payroll_cost, 100*SUM(overtime_pay)/SUM(employer_cost) overtime_share_pct
        FROM v_payroll_dm GROUP BY 1),
att AS (SELECT month, SUM(present_days+0.5*half_days_unpaid)/SUM(scheduled_days) attendance_rate FROM v_attendance_dm GROUP BY 1),
hc AS (SELECT month, 100.0*SUM(exits)/SUM(headcount_start) attrition_pct, SUM(headcount_end) headcount_end
       FROM v_headcount_dm GROUP BY 1),
bud AS (SELECT month, SUM(budget_payroll_cost) budget_payroll FROM budget_payroll_dept_month GROUP BY 1),
tk AS (SELECT date_trunc('month', due_date) AS month,
              100.0*COUNT(*) FILTER (status='Done')/NULLIF(COUNT(*) FILTER (status<>'Cancelled'),0) AS task_completion_pct
       FROM fact_task GROUP BY 1),
ar AS (SELECT period, overdue_receivables, receivables_closing FROM v_ar_month_end),
tg AS (SELECT t.month,
          SUM(attendance_rate_target*hc.headcount_end)/SUM(hc.headcount_end) att_target,
          SUM(overtime_share_target_pct*hc.headcount_end)/SUM(hc.headcount_end) ot_target,
          SUM(attrition_monthly_target_pct*hc.headcount_end)/SUM(hc.headcount_end) attr_target,
          SUM(task_completion_target_pct*hc.headcount_end) FILTER (task_completion_target_pct IS NOT NULL)
            / SUM(hc.headcount_end) FILTER (task_completion_target_pct IS NOT NULL) task_target
       FROM kpi_targets t JOIN fact_headcount_monthly hc ON hc.department_id=t.department_id AND hc.month_start_date=t.month
       GROUP BY 1)
SELECT pl.month, pl.revenue, pl.margin_pct, pay.payroll_cost, bud.budget_payroll,
       100*(pay.payroll_cost-bud.budget_payroll)/bud.budget_payroll AS payroll_vs_budget_pct,
       ar.overdue_receivables, ar.receivables_closing,
       pay.overtime_share_pct, att.attendance_rate*100 AS attendance_pct, hc.attrition_pct, hc.headcount_end,
       tk.task_completion_pct,
       tg.att_target*100 AS attendance_target, tg.ot_target AS overtime_target, tg.attr_target AS attrition_target,
       tg.task_target AS task_target,
       -- no target exists in kpi_targets for these three: provisional reference = average of the previous 12 months
       AVG(pl.revenue)        OVER w AS revenue_ref,
       AVG(pl.margin_pct)     OVER w AS margin_ref,
       AVG(ar.overdue_receivables) OVER w AS overdue_ref
FROM pl LEFT JOIN pay USING (month) LEFT JOIN att USING (month) LEFT JOIN hc USING (month)
LEFT JOIN bud USING (month) LEFT JOIN tk USING (month) LEFT JOIN tg USING (month)
LEFT JOIN ar ON ar.period = pl.period
WINDOW w AS (ORDER BY pl.month ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING)
ORDER BY pl.month"""


class Warehouse:
    """In-memory DuckDB with cleaned tables + metric views."""

    def __init__(self, tables: dict[str, pd.DataFrame] | None = None, clean_log: pd.DataFrame | None = None):
        if tables is None:
            tables, clean_log = load_clean()
        self.tables, self.clean_log = tables, clean_log
        self.con = duckdb.connect()
        for name, df in tables.items():
            self.con.register(name, df)
        extra = {}
        base = tables["dim_employee"].columns  # noqa
        for name, sql in VIEWS.items():
            self.con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")

    def q(self, sql: str, **params) -> pd.DataFrame:
        return self.con.execute(sql, list(params.values()) if params else None).df()

    def view(self, name: str) -> pd.DataFrame:
        return self.con.execute(f"SELECT * FROM {name}").df()
