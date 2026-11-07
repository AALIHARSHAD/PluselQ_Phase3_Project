"""VALIDATE: pandera schemas that must pass on the cleaned data. A failure stops the run loudly.

Row-level problems are handled earlier (rejected). This is the safety net: if anything that
should be impossible is still in the clean data, the pipeline fails and no clean files are written.
"""
from __future__ import annotations

import pandas as pd
import pandera as pa

from . import rules as R
from .rules import RULES, _ts_ok, set_cutoff  # noqa: F401  (set_cutoff re-exported)


class PipelineValidationError(RuntimeError):
    def __init__(self, message, failures: pd.DataFrame):
        super().__init__(message)
        self.failures = failures


def build_schemas() -> dict[str, pa.DataFrameSchema]:
    chk = lambda table: [pa.Check(fn, name=name, error=name) for name, fn in RULES[table]]
    non_neg = lambda: pa.Check(lambda s: s >= 0, name="must be >= 0", error="must be >= 0")
    return {
        "employee": pa.DataFrameSchema(
            {
                "employee_key": pa.Column(nullable=False, unique=True),
                "employee_id": pa.Column(nullable=False),
                "full_name": pa.Column(nullable=False),
                "hire_date": pa.Column(nullable=False, checks=pa.Check(_ts_ok(), name="valid hire date")),
                "exit_date": pa.Column(nullable=True, checks=pa.Check(_ts_ok(), name="valid exit date")),
                "valid_from": pa.Column(nullable=False),
                "valid_to": pa.Column(nullable=True),
                "department_id": pa.Column(nullable=False),
                "role_id": pa.Column(nullable=False),
                "tenure_years": pa.Column(nullable=False, checks=non_neg()),
            },
            checks=chk("employee"), strict=False,
        ),
        "payroll": pa.DataFrameSchema(
            {
                "payroll_item_id": pa.Column(nullable=False, unique=True),
                "employee_id": pa.Column(nullable=False),
                "run_id": pa.Column(nullable=False),
                "period_end_date": pa.Column(nullable=False, checks=pa.Check(_ts_ok("2020-01-01"), name="valid period")),
                "gross_pay": pa.Column(nullable=False, checks=non_neg()),     # no negative salaries
                "net_pay": pa.Column(nullable=False, checks=non_neg()),
                "employer_cost": pa.Column(nullable=False, checks=non_neg()),
                "basic": pa.Column(nullable=False, checks=non_neg()),
            },
            unique=["employee_id", "run_id"], checks=chk("payroll"), strict=False,
        ),
        "salary": pa.DataFrameSchema(
            {
                "payroll_item_id": pa.Column(nullable=False, unique=True),
                "gross_pay": pa.Column(nullable=False, checks=non_neg()),
                "net_pay": pa.Column(nullable=False, checks=non_neg()),
            },
            checks=chk("salary"), strict=False,
        ),
        "attendance": pa.DataFrameSchema(
            {
                "attendance_fact_id": pa.Column(nullable=False, unique=True),
                "employee_id": pa.Column(nullable=False),
                "period_end_date": pa.Column(nullable=False, checks=pa.Check(_ts_ok("2020-01-01"), name="valid period")),
                "attendance_rate": pa.Column(nullable=False, checks=pa.Check(lambda s: (s >= 0) & (s <= 1), name="rate in 0..1")),
            },
            unique=["employee_id", "period_end_date"], checks=chk("attendance"), strict=False,
        ),
        "leave": pa.DataFrameSchema(
            {
                "leave_request_id": pa.Column(nullable=False, unique=True),
                "employee_id": pa.Column(nullable=False),
                "start_date": pa.Column(nullable=False, checks=pa.Check(_ts_ok("2020-01-01", 366), name="valid start")),
                "end_date": pa.Column(nullable=False, checks=pa.Check(_ts_ok("2020-01-01", 366), name="valid end")),
                "days": pa.Column(nullable=False, checks=pa.Check(lambda s: s > 0, name="days > 0")),
            },
            checks=chk("leave"), strict=False,
        ),
    }


def validate_all(clean: dict[str, pd.DataFrame]) -> None:
    """Raise PipelineValidationError listing every broken rule across every table."""
    schemas = build_schemas()
    failures = []
    for table, schema in schemas.items():
        try:
            schema.validate(clean[table], lazy=True)
        except pa.errors.SchemaErrors as exc:
            fc = exc.failure_cases.copy()
            fc.insert(0, "table", table)
            failures.append(fc)
    if failures:
        allf = pd.concat(failures, ignore_index=True)
        summary = allf.groupby(["table", "check"]).size().to_string()
        raise PipelineValidationError(f"Validation FAILED. Broken rules:\n{summary}", allf)
