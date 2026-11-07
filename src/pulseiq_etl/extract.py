"""EXTRACT: read raw CSV exports exactly as delivered. No cleaning happens here."""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("pulseiq.extract")

# name -> required columns (the "contract" with the exporting team)
TABLES = {
    "employee": ["employee_key", "employee_id", "full_name", "hire_date", "exit_date",
                 "employment_status", "department_id", "role_id", "valid_from", "valid_to", "is_current"],
    "payroll": ["payroll_item_id", "run_id", "employee_id", "period_end_date", "department_id", "role_id",
                "gross_pay", "net_pay", "employer_cost", "basic", "lop_days", "payable_days"],
    "salary": ["payroll_item_id", "employee_id", "period_end_date", "gross_pay", "net_pay"],
    "attendance": ["attendance_fact_id", "employee_id", "date_key", "period_end_date", "scheduled_days",
                   "present_days", "attendance_rate"],
    "leave": ["leave_request_id", "employee_id", "leave_type_code", "start_date", "end_date", "days", "status"],
    # small reference tables used for foreign-key checks
    "department": ["department_id", "department_name"],
    "role": ["role_id", "role_title"],
    "leave_type": ["leave_type_code", "leave_type_name"],
}


class MissingInputError(RuntimeError):
    pass


def extract(raw_dir: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for name, required in TABLES.items():
        path = Path(raw_dir) / f"{name}.csv"
        if not path.exists():
            raise MissingInputError(f"Missing input file: {path}")
        df = pd.read_csv(path, dtype=str, keep_default_na=True)  # read all as text; types are fixed in transform
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise MissingInputError(f"{path.name} is missing required columns: {missing}")
        log.info("extract %-10s rows=%d cols=%d", name, len(df), df.shape[1])
        out[name] = df
    return out
