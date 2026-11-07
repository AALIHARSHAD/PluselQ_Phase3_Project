# PulseIQ - ETL pipeline, people analytics and company health (Tasks 1-15)

Extract raw HR exports -> clean with pandas -> validate with pandera -> write clean files + run log.

## Run (one command)
```bash
cp .env.example .env          # optional, defaults work
docker compose run --rm etl   # reads data/raw/*.csv, writes data/clean/, data/rejected/, logs/
docker compose run --rm test  # unit tests
```
Exit code is 0 on success and 1 on any failure (validation, too many rejects, missing file).

## Folders
- `data/raw/` input CSVs (employee, salary, payroll, attendance, leave + department, role, leave_type)
- `data/clean/` cleaned tables (parquet by default)
- `data/rejected/` `rejected_rows.csv`, `corrected_rows.csv`, `validation_failures.csv`
- `logs/` `etl.log`, `run_log.jsonl` (one line per run), `last_run.json`
- `docs/` `metric_dictionary.md`, `decisions.md`
- `scripts/make_raw_exports.py` splits the master workbook into the raw CSVs

## Regenerating raw files
`python scripts/make_raw_exports.py data/PulseIQ_master_dataset.xlsx data/raw`


## Phase 3 - money and insight (Tasks 11-15)
```bash
docker compose up --build phase3          # http://localhost:8502
# or locally:  PYTHONPATH=src streamlit run dashboards/phase3_app.py
docker compose run --rm test              # includes tests/test_phase3.py (tie-outs to the README answer key)
```
| Page | Task | What it proves |
|---|---|---|
| Company health scorecard | 15 | 8 KPIs, target, trend, traffic light; prints on one A4 sheet; every number from `v_company_month` |
| Profit & loss | 11 | Revenue, expense, margin, categories, top vendors; ties to README (Jun 2026 differs by the planted DQ-04, explained on the page) |
| Receivables & cash | 12 | Ageing buckets sum to open receivables = README; days to pay; cash in/out |
| Department impact | 13 | Department x month table equal to `reference_summary_dept_month`; join order explained |
| AI signals | 14 | Anomalies by money at risk, forecast with 80% band, back-tested forecast error, all labelled AI |

Code: metric views in `src/pulseiq_metrics/views.py`, scorecard rules in `src/pulseiq_metrics/scorecard.py`, pages in `dashboards/p3/`.
Decisions and definitions: `docs/decisions.md` (Phase 3 section), `docs/metric_dictionary.md`. Report: `docs/Phase3_Report.md`.
