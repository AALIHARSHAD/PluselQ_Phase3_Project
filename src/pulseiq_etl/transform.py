
"""TRANSFORM: clean, standardise, deduplicate and validate source rows.

Rejected rows are recorded in the Ledger.
Corrected rows are retained and recorded in the Ledger.
"""
from __future__ import annotations

import json

import pandas as pd

EMPLOYEE_DATES = [
    "date_of_birth", "hire_date", "exit_date", "valid_from", "valid_to"
]

# pandas cannot represent the year 9999 as a Timestamp.
# Use pandas' maximum representable date for open-ended dates.
OPEN_ENDED_DATE = pd.Timestamp.max.normalize()


class Ledger:
    """Record rejected and corrected rows with reason codes."""

    def __init__(self):
        self._rej, self._fix = [], []

    @staticmethod
    def _rows(table, df, id_col, reason, detail):
        if df.empty:
            return pd.DataFrame()

        return pd.DataFrame({
            "source_table": table,
            "record_id": df[id_col].astype(str).values,
            "reason_code": reason,
            "detail": detail if isinstance(detail, str) else list(detail),
            "raw_record": [
                json.dumps(
                    {
                        k: None if pd.isna(v) else str(v)
                        for k, v in row.items()
                    },
                    sort_keys=True,
                )
                for row in df.to_dict("records")
            ],
        })

    def reject(self, table, df, id_col, reason, detail=""):
        rows = self._rows(table, df, id_col, reason, detail)
        if len(rows):
            self._rej.append(rows)

    def correct(self, table, df, id_col, reason, detail=""):
        rows = self._rows(table, df, id_col, reason, detail)
        if len(rows):
            self._fix.append(rows)

    def rejected(self):
        return self._finish(self._rej)

    def corrected(self):
        return self._finish(self._fix)

    @staticmethod
    def _finish(parts):
        columns = [
            "source_table", "record_id", "reason_code", "detail", "raw_record"
        ]
        if not parts:
            return pd.DataFrame(columns=columns)

        return (
            pd.concat(parts, ignore_index=True)
            .sort_values(columns[:3] + ["raw_record"])
            .reset_index(drop=True)
        )


# ---------- helpers ----------

def _dates(df, cols):
    """Parse dates and preserve 9999-12-31 as an open-ended date."""
    df = df.copy()
    bad = pd.Series(False, index=df.index)

    for col in cols:
        raw = df[col]
        text = raw.astype("string").str.strip()
        is_open_ended = text.eq("9999-12-31").fillna(False)

        # Replace the unsupported year-9999 sentinel with a pandas-compatible
        # maximum date. Keep actual missing values as NaT.
        values = raw.mask(is_open_ended, OPEN_ENDED_DATE)

        parsed = pd.to_datetime(
            values,
            errors="coerce",
        )

        invalid = parsed.isna() & raw.notna() & ~is_open_ended
        bad |= invalid
        df[col] = parsed

    return df, bad


def _numbers(df, cols):
    df = df.copy()
    bad = pd.Series(False, index=df.index)

    for col in cols:
        raw = df[col]
        parsed = pd.to_numeric(raw, errors="coerce")
        bad |= parsed.isna() & raw.notna()
        df[col] = parsed

    return df, bad


def _clean_text(series):
    return series.str.replace(r"\s+", " ", regex=True).str.strip()


def _clean_name(series):
    """Fix all-uppercase or all-lowercase names without changing mixed casing."""
    series = _clean_text(series)
    shouty = series.notna() & (
        (series == series.str.upper())
        | (series == series.str.lower())
    )
    return series.where(~shouty, series.str.title())


def _split(df, bad, table, id_col, ledger, reason, detail):
    if bad.any():
        ledger.reject(table, df[bad], id_col, reason, detail)
    return df[~bad].copy()


def _drop_dupes(df, subset, order_col, table, id_col, ledger, reason):
    df = df.sort_values(order_col, kind="mergesort")
    duplicates = df.duplicated(subset, keep="first")

    if duplicates.any():
        ledger.reject(
            table, df[duplicates], id_col, reason,
            "duplicate of " + "+".join(subset),
        )

    return df[~duplicates].copy()


def _ym(df, col, prefix):
    df[f"{prefix}_year"] = df[col].dt.year.astype("Int64")
    df[f"{prefix}_month"] = df[col].dt.month.astype("Int64")
    df[f"{prefix}_year_month"] = df[col].dt.strftime("%Y-%m")
    return df


# ---------- employee ----------

def transform_employee(raw, refs, ledger, cutoff):
    table = "employee"
    df = raw.copy()

    text_cols = [
        "employee_id", "department_id", "role_id", "employment_status",
        "employment_type", "work_location", "work_mode", "role_title",
        "manager_id", "gender", "is_current", "change_reason",
    ]
    for col in text_cols:
        if col in df:
            df[col] = _clean_text(df[col])

    df["full_name"] = _clean_name(df["full_name"])
    df["employee_id"] = df["employee_id"].str.upper()

    df, bad = _numbers(df, ["employee_key", "job_level"])
    df = _split(
        df, bad, table, "employee_key", ledger,
        "INVALID_NUMBER", "non-numeric employee_key/job_level",
    )
    df["employee_key"] = df["employee_key"].astype("int64")

    df, bad = _dates(df, EMPLOYEE_DATES)
    df = _split(
        df, bad, table, "employee_key", ledger,
        "INVALID_DATE", "date not in YYYY-MM-DD format",
    )

    df = _drop_dupes(
        df, ["employee_key"], "employee_key", table, "employee_key",
        ledger, "DUPLICATE_KEY",
    )

    # Quarantine all versions of an employee whose hire date is after exit.
    bad_ids = set(
        df.loc[
            df["exit_date"].notna()
            & (df["hire_date"] > df["exit_date"]),
            "employee_id",
        ]
    )
    df = _split(
        df, df["employee_id"].isin(bad_ids), table, "employee_key",
        ledger, "HIRE_AFTER_EXIT",
        "hire_date > exit_date; fix at source",
    )

    bad = (
        ~df["department_id"].isin(refs["department"]["department_id"])
        | ~df["role_id"].isin(refs["role"]["role_id"])
    )
    df = _split(
        df, bad, table, "employee_key", ledger,
        "ORPHAN_FOREIGN_KEY",
        "department_id or role_id not in reference",
    )

    # Resolve SCD overlaps by ending a version the day before the next starts.
    df = df.sort_values(
        ["employee_id", "valid_from", "employee_key"],
        kind="mergesort",
    ).reset_index(drop=True)

    next_start = df.groupby("employee_id")["valid_from"].shift(-1)
    overlap = next_start.notna() & (
        df["valid_to"].isna() | (df["valid_to"] >= next_start)
    )

    df["valid_to_adjusted"] = overlap

    if overlap.any():
        ledger.correct(
            table, df[overlap], "employee_key",
            "SCD_OVERLAP_FIXED",
            "valid_to set to next valid_from - 1 day",
        )
        df.loc[overlap, "valid_to"] = (
            next_start[overlap] - pd.Timedelta(days=1)
        )

    cutoff_ts = pd.Timestamp(cutoff)
    end = df["exit_date"].fillna(cutoff_ts).clip(upper=cutoff_ts)

    df["tenure_years"] = (
        (end - df["hire_date"]).dt.days / 365.25
    ).round(2)

    df = _ym(df, "hire_date", "hire")
    df["exit_year"] = df["exit_date"].dt.year.astype("Int64")
    df["is_current_flag"] = df["is_current"].eq("Y")

    return df.sort_values("employee_key").reset_index(drop=True)


# ---------- payroll ----------

def transform_payroll(raw, emp, refs, ledger):
    table = "payroll"
    df = raw.copy()

    text_cols = [
        "payroll_item_id", "run_id", "employee_id",
        "department_id", "role_id", "variable_pay_type",
    ]
    for col in text_cols:
        if col in df:
            df[col] = _clean_text(df[col])

    df["employee_id"] = df["employee_id"].str.upper()

    number_cols = [
        "gross_pay", "net_pay", "employer_cost", "basic", "lop_days",
        "payable_days", "overtime_pay", "variable_pay", "total_deductions",
        "employee_key", "date_key", "monthly_fixed_gross",
        "overtime_hours_paid",
    ]
    df, bad = _numbers(
        df, [col for col in number_cols if col in df]
    )
    df = _split(
        df, bad, table, "payroll_item_id", ledger,
        "INVALID_NUMBER", "non-numeric money/day field",
    )

    df, bad = _dates(df, ["period_end_date"])
    df = _split(
        df, bad, table, "payroll_item_id", ledger,
        "INVALID_DATE", "period_end_date not YYYY-MM-DD",
    )

    df = _drop_dupes(
        df, ["employee_id", "run_id"], "payroll_item_id",
        table, "payroll_item_id", ledger, "DUPLICATE_PAYROLL_ROW",
    )

    df = _split(
        df, ~df["employee_id"].isin(emp["employee_id"]),
        table, "payroll_item_id", ledger,
        "ORPHAN_FOREIGN_KEY", "employee_id not in employee",
    )

    money_cols = ["gross_pay", "net_pay", "employer_cost", "basic"]
    bad = (df[money_cols] < 0).any(axis=1)
    df = _split(
        df, bad, table, "payroll_item_id", ledger,
        "NEGATIVE_AMOUNT", "negative money value",
    )

    if {"variable_pay_type", "variable_pay"} <= set(df.columns):
        no_variable_pay = (
            df["variable_pay_type"].isna()
            & (df["variable_pay"].fillna(0) == 0)
        )
        df.loc[no_variable_pay, "variable_pay_type"] = "None"

    df = _ym(df, "period_end_date", "period")

    return df.sort_values(
        ["period_end_date", "employee_id", "payroll_item_id"]
    ).reset_index(drop=True)


# ---------- attendance ----------

def transform_attendance(raw, emp, refs, ledger):
    table = "attendance"
    df = raw.copy()

    for col in ["attendance_fact_id", "employee_id", "department_id"]:
        df[col] = _clean_text(df[col])

    df["employee_id"] = df["employee_id"].str.upper()

    number_cols = [
        "scheduled_days", "present_days", "wfh_days", "half_days_unpaid",
        "paid_leave_days", "unpaid_absence_days", "late_arrivals",
        "avg_hours_worked", "overtime_hours", "attendance_rate",
        "date_key", "employee_key",
    ]
    df, bad = _numbers(df, [col for col in number_cols if col in df])
    df = _split(
        df, bad, table, "attendance_fact_id", ledger,
        "INVALID_NUMBER", "non-numeric field",
    )

    df, bad = _dates(df, ["period_end_date"])
    df = _split(
        df, bad, table, "attendance_fact_id", ledger,
        "INVALID_DATE", "period_end_date not YYYY-MM-DD",
    )

    df = _drop_dupes(
        df, ["employee_id", "period_end_date"], "attendance_fact_id",
        table, "attendance_fact_id", ledger, "DUPLICATE_ATTENDANCE_ROW",
    )

    df = _split(
        df, ~df["employee_id"].isin(emp["employee_id"]),
        table, "attendance_fact_id", ledger,
        "ORPHAN_FOREIGN_KEY", "employee_id not in employee",
    )

    # Reject attendance outside the employee's employment period.
    life = emp.groupby("employee_id").agg(
        hire=("hire_date", "min"),
        exit=("exit_date", "max"),
    )
    df = df.join(life, on="employee_id")

    month_start = df["period_end_date"].dt.to_period("M").dt.to_timestamp()
    bad = (
        (df["exit"].notna() & (month_start > df["exit"]))
        | (df["period_end_date"] < df["hire"])
    )
    df = df.drop(columns=["hire", "exit"])

    df = _split(
        df, bad, table, "attendance_fact_id", ledger,
        "ATTENDANCE_OUTSIDE_EMPLOYMENT",
        "month is after exit_date or before hire_date",
    )

    bad = (
        (df["attendance_rate"] < 0)
        | (df["attendance_rate"] > 1)
        | (df["present_days"] > df["scheduled_days"])
    )
    df = _split(
        df, bad, table, "attendance_fact_id", ledger,
        "IMPOSSIBLE_ATTENDANCE",
        "rate outside 0-1 or present > scheduled",
    )

    df = _ym(df, "period_end_date", "period")

    return df.sort_values(
        ["period_end_date", "employee_id", "attendance_fact_id"]
    ).reset_index(drop=True)


# ---------- leave ----------

def transform_leave(raw, emp, refs, ledger, cutoff):
    table = "leave"
    df = raw.copy()

    for col in [
        "leave_request_id", "employee_id", "leave_type_code",
        "status", "approver_id",
    ]:
        df[col] = _clean_text(df[col])

    df["employee_id"] = df["employee_id"].str.upper()
    df["leave_type_code"] = df["leave_type_code"].str.upper()

    df, bad = _numbers(df, ["days"])
    df = _split(
        df, bad, table, "leave_request_id", ledger,
        "INVALID_NUMBER", "non-numeric days",
    )

    df, bad = _dates(
        df, ["start_date", "end_date", "applied_on", "decided_on"]
    )
    df = _split(
        df, bad, table, "leave_request_id", ledger,
        "INVALID_DATE", "date not YYYY-MM-DD",
    )

    df = _drop_dupes(
        df, ["leave_request_id"], "leave_request_id",
        table, "leave_request_id", ledger, "DUPLICATE_LEAVE_ROW",
    )

    bad = (
        ~df["employee_id"].isin(emp["employee_id"])
        | ~df["leave_type_code"].isin(
            refs["leave_type"]["leave_type_code"]
        )
    )
    df = _split(
        df, bad, table, "leave_request_id", ledger,
        "ORPHAN_FOREIGN_KEY",
        "employee_id or leave_type_code unknown",
    )

    # If dates are reversed, swap them and log the correction.
    swapped = df["end_date"] < df["start_date"]
    df["dates_swapped_fixed"] = swapped

    if swapped.any():
        ledger.correct(
            table, df[swapped], "leave_request_id",
            "LEAVE_DATES_SWAPPED_FIXED",
            "start_date and end_date swapped back",
        )
        start = df.loc[swapped, "start_date"].copy()
        end = df.loc[swapped, "end_date"].copy()
        df.loc[swapped, "start_date"] = end
        df.loc[swapped, "end_date"] = start

    df = _split(
        df, df["days"] <= 0, table, "leave_request_id", ledger,
        "NON_POSITIVE_DAYS", "days <= 0",
    )

    df["start_date_key"] = (
        df["start_date"].dt.strftime("%Y%m%d").astype("int64")
    )
    df["end_date_key"] = (
        df["end_date"].dt.strftime("%Y%m%d").astype("int64")
    )
    df = _ym(df, "start_date", "start")

    return df.sort_values(
        ["start_date", "leave_request_id"]
    ).reset_index(drop=True)


# ---------- salary ----------

def transform_salary(raw, pay, ledger):
    """Ensure salary exports agree with clean payroll rows."""
    table = "salary"
    df = raw.copy()

    for col in ["payroll_item_id", "employee_id"]:
        df[col] = _clean_text(df[col])

    df["employee_id"] = df["employee_id"].str.upper()

    number_cols = [
        "employee_key", "monthly_fixed_gross", "basic", "hra",
        "earned_fixed_pay", "gross_pay", "net_pay",
    ]
    df, bad = _numbers(
        df, [col for col in number_cols if col in df]
    )
    df = _split(
        df, bad, table, "payroll_item_id", ledger,
        "INVALID_NUMBER", "non-numeric money field",
    )

    df, bad = _dates(df, ["period_end_date"])
    df = _split(
        df, bad, table, "payroll_item_id", ledger,
        "INVALID_DATE", "period_end_date not YYYY-MM-DD",
    )

    df = _drop_dupes(
        df, ["payroll_item_id"], "payroll_item_id",
        table, "payroll_item_id", ledger, "DUPLICATE_SALARY_ROW",
    )

    df = _split(
        df, ~df["payroll_item_id"].isin(pay["payroll_item_id"]),
        table, "payroll_item_id", ledger,
        "NOT_IN_CLEAN_PAYROLL",
        "payroll row was rejected or missing",
    )

    df = df.merge(
        pay[["payroll_item_id", "gross_pay", "net_pay"]],
        on="payroll_item_id",
        suffixes=("", "_payroll"),
    )

    bad = (
        (df["gross_pay"] - df["gross_pay_payroll"]).abs() > 0.01
    ) | (
        (df["net_pay"] - df["net_pay_payroll"]).abs() > 0.01
    )

    df = _split(
        df, bad, table, "payroll_item_id", ledger,
        "SALARY_PAYROLL_MISMATCH", "gross/net differ from payroll",
    )

    df = df.drop(columns=["gross_pay_payroll", "net_pay_payroll"])

    bad = (df[["gross_pay", "net_pay"]] < 0).any(axis=1)
    df = _split(
        df, bad, table, "payroll_item_id", ledger,
        "NEGATIVE_AMOUNT", "negative pay",
    )

    df = _ym(df, "period_end_date", "period")

    return df.sort_values(
        ["period_end_date", "employee_id", "payroll_item_id"]
    ).reset_index(drop=True)
