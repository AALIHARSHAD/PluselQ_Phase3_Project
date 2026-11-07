"""One-off helper: split the master workbook into the raw CSV exports the ETL reads.

Usage: python scripts/make_raw_exports.py <workbook.xlsx> [out_dir]
The ETL itself never reads the xlsx; it only reads data/raw/*.csv (like a real export drop).
"""
import sys
from pathlib import Path
import pandas as pd

SHEETS = {
    "dim_employee": "employee",
    "fact_payroll": "payroll",
    "fact_attendance_monthly": "attendance",
    "fact_leave": "leave",
    "dim_department": "department",
    "dim_role": "role",
    "dim_leave_type": "leave_type",
    "metric_dictionary": "metric_dictionary",
}

def main(xlsx, out="data/raw"):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for sheet, name in SHEETS.items():
        df = pd.read_excel(xlsx, sheet_name=sheet)
        df.to_csv(out / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        print(f"{name}.csv  {len(df)} rows")

if __name__ == "__main__":
    main(*sys.argv[1:3])
