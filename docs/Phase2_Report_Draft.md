# PulseIQ — Phase 2 Report (Draft)

**Name:** Aali Harshad  
**Track:** Data Analytics  
**Phase:** 2 — People, Teams, Cost and Budget  
**Repository:** https://github.com/AALIHARSHAD/PulseIQ_ETL_Project  
**Git tag:** `phase-2` (create only after reviewing and committing the completed work)

## Task evidence checklist

| Task | Status | Evidence to attach |
|---|---|---|
| Task 6 — Attendance and leave | Dashboard page implemented; verify in Docker | Screenshot of attendance/leave page + three findings |
| Task 7 — Attrition | Dashboard page implemented; verify suppression and prediction label | Screenshot + three findings |
| Task 8 — Team productivity | Dashboard page implemented; manually verify two teams before claiming completion | Screenshot + verification table |
| Task 9 — Payroll reconciliation | Reconciliation table implemented; investigate differences before excluding any rows | Screenshot + reconciliation and excluded-row rationale |
| Task 10 — Budget and KPI targets | Variance table and ranking implemented; confirm target traffic-light rules | Screenshot + three hand-checked department-months |

## Proof it works
After running `docker compose up --build dashboard`, open `http://localhost:8501`. Add screenshots here after validating each page. Run `docker compose run --rm test` and paste the actual test output; do not claim tests passed unless they pass.

## Data-driven observations to validate
- The source attendance fact covers April 2025 through September 2026 (18 months), with 11 departments.
- Across that attendance fact, there are 150,155 scheduled days and 141,139 present days; weighted attendance is approximately 94.0%.
- The source attendance fact records 9,632 late arrivals and 9,814 overtime hours.
- Leave source status counts: Approved 3,088 requests / 7,276 days; Cancelled 109 / 223 days; Pending 34 / 66 days; Rejected 210 / 434 days. Approved leave is used for approved-leave trend visuals.

These are source-data summaries, not causal claims. Holiday timing alone does not prove that a holiday caused an attendance dip.

## What I learned (rewrite in your own words before submission)
I learned to distinguish rates from counts and to calculate attendance using scheduled working days as the denominator. I separated actual exits from predicted risk and applied group-level privacy suppression. I also learned that payroll and budget figures must be reconciled and their variance sign rules documented before presenting recommendations.

## Problems and resolutions
- The warehouse available in the original project bundle did not contain all Phase 2 source tables. The dashboard therefore reads the provided master workbook sheets directly for these pages.
- Payroll reconciliation differences must be investigated against the supplied answer key; rows must not be excluded merely to force totals to match.
- KPI target columns do not themselves specify every traffic-light threshold. Confirm the programme's intended rules before treating status labels as operational decisions.

## Next phase plan
After validating and documenting all five pages, proceed to the next phase's revenue, cash and AI-signal work, preserving privacy controls and source-to-chart lineage.
