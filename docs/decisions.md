# Data-quality decisions (Task 1)

| Situation | Rule | Why |
|---|---|---|
| **hire_date after exit_date** (the "think for yourself" case) | **Quarantine** every version of that employee: removed from clean data, saved in `rejected_rows.csv` as `HIRE_AFTER_EXIT`, counted in the run log. Fix at source. | Dropping silently hides a person from headcount. "Fixing" means guessing which date is wrong, and either guess corrupts tenure, headcount and attrition. Quarantine keeps the evidence and keeps the numbers honest. Rows that depend on that person (payroll, attendance) are rejected as orphans. |
| Duplicate payroll row (same employee + run) | Keep lowest `payroll_item_id`, reject the copy | Overstates pay if kept |
| Payroll for unknown employee | Reject (`ORPHAN_FOREIGN_KEY`) | Money cannot be assigned to anyone |
| Attendance after exit / before hire | Reject (`ATTENDANCE_OUTSIDE_EMPLOYMENT`) | Impossible; cannot tell which side is wrong |
| Leave end date before start date | **Fix** by swapping, flag `dates_swapped_fixed`, list in `corrected_rows.csv` | Pattern is clearly swapped dates; nothing is lost |
| SCD versions overlap (valid_to runs into next valid_from) | **Fix**: `valid_to = next valid_from - 1 day`, flag `valid_to_adjusted` | The next version's start is the authoritative change date; otherwise facts join to two versions |
| Missing `variable_pay_type` with zero variable pay | Fill with `"None"` | Normal case, make it explicit |
| Negative pay | Reject, never `abs()` | A sign error may hide a bigger problem |
| Reject rate above `MAX_REJECT_PCT` (2%) | Run **fails**, nothing written to `clean/` | A few bad rows are normal; many means the source is broken |

Repeatability: output sorted deterministically, no `today()` (a fixed `DATA_CUTOFF_DATE` is used for tenure), atomic file replace. The run log stores a SHA-256 of every output file so two runs can be compared.


# Phase 3 decisions (Tasks 11-15)

| Situation | Rule | Why |
|---|---|---|
| Group accounts (4000 Income, 5000 Expenses, etc.) | Excluded from every P&L number (`is_group = 'N'` only) | A heading and its children would be counted twice |
| Revenue definition | Detail income accounts 4001-4004 **plus 4900 interest** | This is what the README answer key uses; M16 text names only 4001-4004, noted on the page |
| June 2026 ledger expense is 18,450 above the README | Not removed; flagged as DQ-04 (JE-002094). Same amount is the payroll-vs-ledger gap | The entry balances, so only the ledger owner can say which side is wrong |
| Open invoice statuses | SENT, OVERDUE, PARTIALLY_PAID. DRAFT and CANCELLED are not receivables, PAID is closed | Task 12 brief |
| "Not yet due" invoices | Shown as their own bucket, so the four ageing buckets (0-30, 31-60, 61-90, 90+) mean days *past due* | Buckets still add to total open receivables |
| Days to pay | Last payment date minus invoice date, paid invoices only | A part-paid invoice has no final pay date yet |
| Department join | Aggregate each source to department x month first, then LEFT JOIN from payroll | Joining raw rows repeats payroll once per attendance row |
| Groups under 5 people | Hidden in charts/tables (Executive Office has 1), kept in reconciliation totals | Minimum group size in the metric dictionary |
| Forecast error | `fact_forecast` ends at the last actual month, so no stored forecast has an actual yet. Error is measured by back-testing the documented method from earlier months; labelled as my back-test | Honest alternative to inventing an error figure |
| Scorecard traffic light | GREEN = on the good side of target; AMBER = bad side but inside a tolerance (attendance 1 pt, attrition 0.5 pt, overtime 0.5 pt, task completion 5 pts, payroll +2% over budget); RED = beyond. Thresholds live in `scorecard.py` | kpi_targets gives targets but no thresholds. **Confirm these with the founder/finance** |
| KPIs with no target in `kpi_targets` (revenue, margin, overdue receivables) | Judged against the average of the previous 12 months (amber: revenue and overdue within 10%, margin within 3 pts), marked "provisional"; first month is grey | Never invent a target; show the reference used |
