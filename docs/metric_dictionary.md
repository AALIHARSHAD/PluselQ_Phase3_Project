# PulseIQ Metric Dictionary (v0.1, first 5 metrics)

Official names, definitions and formulas come from the master dataset's `metric_dictionary` sheet. Chart titles in later tasks must use these exact names. The *Clean-data lineage* line shows which columns from Task 1 feed each metric.

Privacy rule: never show a group smaller than **minimum group size** (a group of one reveals one person).

## M01 - Headcount

| Field | Value |
|---|---|
| Business definition | Active employees on the last day of the month (permanent and contract). |
| Formula | `COUNT(DISTINCT employee_id) with hire_date <= month_end AND (exit_date IS NULL OR exit_date > month_end)` |
| Grain | Department x month |
| Time period | Month end |
| Unit | count |
| Good direction | Context dependent |
| Owner | HR Analytics |
| Source table | fact_headcount_monthly / dim_employee |
| Clean-data lineage | employee.hire_date, employee.exit_date, employee.employee_id (latest version per employee; Task 2 builds fact_headcount_monthly) |
| Caveat | Excludes CEO if you compare departments only |
| Minimum group size | 5 |

## M02 - Hires

| Field | Value |
|---|---|
| Business definition | Employees whose hire_date falls in the month. |
| Formula | `COUNT(employee_id) where hire_date in month` |
| Grain | Department x month |
| Time period | Month |
| Unit | count |
| Good direction | Context dependent |
| Owner | HR Analytics |
| Source table | fact_headcount_monthly |
| Clean-data lineage | employee.hire_date / hire_year_month |
| Caveat | Transfers are not hires |
| Minimum group size | 5 |

## M03 - Exits

| Field | Value |
|---|---|
| Business definition | Employees whose exit_date falls in the month (resigned, terminated or contract ended). |
| Formula | `COUNT(employee_id) where exit_date in month` |
| Grain | Department x month |
| Time period | Month |
| Unit | count |
| Good direction | Lower is better |
| Owner | HR Analytics |
| Source table | fact_headcount_monthly |
| Clean-data lineage | employee.exit_date / exit_year |
| Caveat | - |
| Minimum group size | 5 |

## M04 - Attrition rate (monthly)

| Field | Value |
|---|---|
| Business definition | Share of people who left in the month. |
| Formula | `Exits / headcount_start x 100` |
| Grain | Department x month |
| Time period | Month |
| Unit | percent |
| Good direction | Lower is better |
| Owner | HR Analytics |
| Source table | fact_headcount_monthly |
| Clean-data lineage | M03 and M01 at month start |
| Caveat | Very noisy for small departments |
| Minimum group size | 10 |

## M05 - Attrition rate (rolling 12 months)

| Field | Value |
|---|---|
| Business definition | Leavers in the last 12 months divided by average headcount over the same months. |
| Formula | `SUM(exits, 12m) / AVG(headcount_end, 12m) x 100` |
| Grain | Department x month |
| Time period | 12 months |
| Unit | percent |
| Good direction | Lower is better |
| Owner | HR Analytics |
| Source table | fact_headcount_monthly |
| Clean-data lineage | M03 summed over 12 months and M01 averaged over the same months |
| Caveat | Use for headline reporting; monthly is too noisy |
| Minimum group size | 10 |


# Phase 3 metrics (from the master metric_dictionary sheet)

Scorecard KPIs are M09, M11, M13, M16, M18, M21, M04, M22. The **Metric view** line is where the number is computed in this project.

## M09 - Payroll cost (employer cost)

| Field | Value |
|---|---|
| Business definition | Full cost of employees to the company: gross pay plus employer PF and ESI. |
| Formula | `SUM(employer_cost)` |
| Unit | INR |
| Good direction | Lower is better when output is equal |
| Metric view | v_payroll_dm, v_company_month |
| Caveat | Must reconcile with ledger accounts 5001-5005 |

## M11 - Overtime share

| Field | Value |
|---|---|
| Business definition | How much of payroll cost is overtime pay. |
| Formula | `SUM(overtime_pay) / SUM(employer_cost) x 100` |
| Unit | percent |
| Good direction | Lower is better |
| Metric view | v_payroll_dm |
| Caveat | Only overtime-eligible roles earn overtime |

## M13 - Attendance rate

| Field | Value |
|---|---|
| Business definition | Days present (half day counts 0.5) divided by scheduled working days. |
| Formula | `(SUM(present_days) + 0.5 x SUM(half_days_unpaid)) / SUM(scheduled_days)` |
| Unit | ratio |
| Good direction | Higher is better |
| Metric view | v_attendance_dm |
| Caveat | Paid leave counts as not present |

## M16 - Revenue

| Field | Value |
|---|---|
| Business definition | Income booked in the ledger (accounts 4001-4004). |
| Formula | `-SUM(signed_amount) for accounts 4001-4004` |
| Unit | INR |
| Good direction | Higher is better |
| Metric view | v_pl_monthly |
| Caveat | Excludes GST (booked to 2200) |

## M17 - Net profit

| Field | Value |
|---|---|
| Business definition | Revenue minus all expenses (4xxx less 5xxx). |
| Formula | `-SUM(signed_amount) for accounts 4xxx and 5xxx` |
| Unit | INR |
| Good direction | Higher is better |
| Metric view | v_pl_monthly |
| Caveat | Interest income (4900) is included |

## M18 - Operating margin

| Field | Value |
|---|---|
| Business definition | Net profit as a share of revenue. |
| Formula | `Net profit / Revenue x 100` |
| Unit | percent |
| Good direction | Higher is better |
| Metric view | v_pl_monthly |
| Caveat | nan |

## M19 - Payroll as % of revenue

| Field | Value |
|---|---|
| Business definition | Share of revenue consumed by payroll cost. |
| Formula | `Payroll cost / Revenue x 100` |
| Unit | percent |
| Good direction | Lower is better |
| Metric view | v_company_month (payroll_cost / revenue) |
| Caveat | Use ledger payroll accounts to avoid mismatch |

## M20 - Days sales outstanding (DSO)

| Field | Value |
|---|---|
| Business definition | Average days to collect: receivables divided by credit sales x days. |
| Formula | `Closing receivables / revenue incl GST (last 90 days) x 90` |
| Unit | days |
| Good direction | Lower is better |
| Metric view | Receivables page (approx.) |
| Caveat | Carried-in invoices included |

## M21 - Overdue receivables

| Field | Value |
|---|---|
| Business definition | Unpaid invoice balance past due date at the report date. |
| Formula | `SUM(balance_due) where due_date < report date and status not DRAFT/CANCELLED` |
| Unit | INR |
| Good direction | Lower is better |
| Metric view | v_ar_open, v_ar_month_end |
| Caveat | nan |

## M22 - Task completion rate

| Field | Value |
|---|---|
| Business definition | Tasks done divided by tasks planned in the sprint (cancelled tasks excluded). |
| Formula | `COUNT(status = Done) / COUNT(status != Cancelled)` |
| Unit | percent |
| Good direction | Higher is better |
| Metric view | v_company_month |
| Caveat | Sample feed until the live board is ready |

## M26 - Anomaly flag rate

| Field | Value |
|---|---|
| Business definition | Share of scored records flagged by the AI anomaly service. |
| Formula | `COUNT(flagged = Y) / COUNT(*)` |
| Unit | percent |
| Good direction | Context dependent |
| Metric view | v_anomaly_type |
| Caveat | Flags are leads, not proof |

## M27 - High-risk share

| Field | Value |
|---|---|
| Business definition | Share of employees in the High attrition-risk band. |
| Formula | `COUNT(risk_band = High) / COUNT(*)` |
| Unit | percent |
| Good direction | Lower is better |
| Metric view | fact_attrition_risk (AI page) |
| Caveat | Show by group only; never rank named people |

## M28 - Forecast error (MAPE)

| Field | Value |
|---|---|
| Business definition | Average absolute percentage error of headcount forecasts versus actuals. |
| Formula | `AVG(ABS(actual - forecast) / actual) x 100` |
| Unit | percent |
| Good direction | Lower is better |
| Metric view | forecast.py back-test |
| Caveat | Needs actuals for the forecast months |

Note on M16: the sheet formula names accounts 4001-4004, but the README answer key includes 4900 interest income; this project follows the answer key and says so on the P&L page.
