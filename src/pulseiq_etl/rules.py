"""Validation rules as plain pandas functions (True = row is OK). No pandera needed, so they are
unit-testable anywhere. validate.py plugs these same functions into pandera schemas."""
import pandas as pd

CUTOFF = pd.Timestamp("2026-09-30")  # overwritten by set_cutoff()


def set_cutoff(cutoff: str):
    global CUTOFF
    CUTOFF = pd.Timestamp(cutoff)


def _ts_ok(lo="2000-01-01", slack_days=0):
    def fn(s: pd.Series) -> pd.Series:
        hi = CUTOFF + pd.Timedelta(days=slack_days)
        return s.isna() | ((s >= pd.Timestamp(lo)) & (s <= hi))
    return fn


# --- cross-row rules: each takes the whole frame and returns a boolean Series (True = OK) ---
def one_current_version_per_employee(df):
    n = df.groupby("employee_id")["is_current"].transform(lambda s: (s == "Y").sum())
    return n == 1


def no_scd_overlap(df):
    d = df.sort_values(["employee_id", "valid_from"])
    nxt = d.groupby("employee_id")["valid_from"].shift(-1)
    return (nxt.isna() | (d["valid_to"] < nxt)).reindex(df.index)


def hire_not_after_exit(df):
    return df["exit_date"].isna() | (df["hire_date"] <= df["exit_date"])


def version_dates_ordered(df):
    return df["valid_to"].isna() | (
        df["valid_from"] <= df["valid_to"]
    )


def net_not_above_gross(df):
    return df["net_pay"] <= df["gross_pay"] + 0.005


def present_not_above_scheduled(df):
    return df["present_days"] <= df["scheduled_days"]


def leave_end_not_before_start(df):
    return df["end_date"] >= df["start_date"]


def is_datetime(col):
    return lambda df: pd.Series(pd.api.types.is_datetime64_any_dtype(df[col]), index=df.index)


RULES = {
    "employee": [
        ("exactly one current version per employee", one_current_version_per_employee),
        ("no overlapping SCD versions", no_scd_overlap),
        ("hire_date not after exit_date", hire_not_after_exit),
        ("valid_from <= valid_to", version_dates_ordered),
        ("hire_date is a datetime", is_datetime("hire_date")),
    ],
    "payroll": [
        ("net_pay <= gross_pay", net_not_above_gross),
        ("period_end_date is a datetime", is_datetime("period_end_date")),
    ],
    "salary": [("net_pay <= gross_pay", net_not_above_gross)],
    "attendance": [("present_days <= scheduled_days", present_not_above_scheduled)],
    "leave": [("end_date >= start_date", leave_end_not_before_start)],
}




def check_rules_only(clean):
    """Pandas-only runner for the cross-row RULES (used by unit tests; the pipeline uses pandera)."""
    bad = {}
    for table, rules in RULES.items():
        for name, fn in rules:
            n = int((~fn(clean[table]).astype(bool)).sum())
            if n:
                bad[(table, name)] = n
    return bad
