import hashlib
import shutil
from pathlib import Path

import pandas as pd
import pytest

from pulseiq_etl.config import Config
from pulseiq_etl.pipeline import RejectThresholdError, run
from pulseiq_etl.rules import check_rules_only, set_cutoff
from pulseiq_etl.transform import Ledger, transform_employee

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def rules_validator(clean):
    bad = check_rules_only(clean)
    if bad:
        raise RuntimeError(f"rules broken: {bad}")


def make_cfg(tmp_path, raw=RAW, fmt="csv", max_pct=2.0):
    return Config(raw_dir=raw, clean_dir=tmp_path / "clean", rejected_dir=tmp_path / "rej",
                  log_dir=tmp_path / "logs", output_format=fmt, cutoff_date="2026-09-30", max_reject_pct=max_pct)


@pytest.fixture
def validator():
    # Use the real pandera validation when installed (Docker); otherwise the pandas-only rules.
    try:
        import pandera  # noqa: F401
        from pulseiq_etl.validate import validate_all
        return validate_all
    except ImportError:
        return rules_validator


def hashes(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).glob("*.csv"))}


def test_known_bad_rows_are_rejected_and_counted(tmp_path, validator):
    s = run(make_cfg(tmp_path), validator)
    t = s["tables"]
    assert t["payroll"]["rejected"] == 4 and t["payroll"]["rows_out"] == 7340
    assert t["attendance"]["rejected"] == 4
    assert t["leave"]["corrected"] == 2 and t["employee"]["corrected"] == 1
    rej = pd.read_csv(tmp_path / "rej" / "rejected_rows.csv")
    assert len(rej) == 12 and set(rej.reason_code) == {
        "DUPLICATE_PAYROLL_ROW", "ORPHAN_FOREIGN_KEY", "ATTENDANCE_OUTSIDE_EMPLOYMENT", "NOT_IN_CLEAN_PAYROLL"}
    assert t["salary"]["rows_out"] == 7340


def test_running_twice_gives_identical_output(tmp_path, validator):
    cfg = make_cfg(tmp_path)
    run(cfg, validator)
    first = hashes(cfg.clean_dir)
    run(cfg, validator)
    assert hashes(cfg.clean_dir) == first and len(first) == 5


def test_payroll_matches_reconciliation_answer_key(tmp_path, validator):
    xlsx = list(Path(__file__).resolve().parents[1].glob("data/*.xlsx"))
    if not xlsx:
        pytest.skip("answer key workbook not in data/")
    key = pd.read_excel(xlsx[0], sheet_name="reconciliation_answer_key")
    cfg = make_cfg(tmp_path)
    run(cfg, validator)
    p = pd.read_csv(cfg.clean_dir / "payroll.csv")
    got = p.groupby("period_year_month")["gross_pay"].sum().round(2)
    exp = key.assign(m=key["month"].astype(str).str[:7]).set_index("m")["payroll_gross_pay"].round(2)
    assert (got - exp).abs().max() < 0.01


def test_reject_threshold_fails_loudly(tmp_path, validator):
    raw = tmp_path / "raw"
    shutil.copytree(RAW, raw)
    p = pd.read_csv(raw / "payroll.csv", dtype=str)
    p["gross_pay"] = "-5"          # every salary negative
    p.to_csv(raw / "payroll.csv", index=False)
    with pytest.raises(RejectThresholdError):
        run(make_cfg(tmp_path, raw=raw), validator)
    assert not (tmp_path / "clean" / "payroll.csv").exists()   # nothing half-written


def test_hire_after_exit_is_quarantined_not_guessed():
    set_cutoff("2026-09-30")
    emp = pd.read_csv(RAW / "employee.csv", dtype=str)
    emp.loc[emp.employee_id == "EMP-0002", ["hire_date", "exit_date"]] = ["2024-05-01", "2023-01-01"]
    refs = {k: pd.read_csv(RAW / f"{k}.csv", dtype=str) for k in ("department", "role")}
    led = Ledger()
    out = transform_employee(emp, refs, led, "2026-09-30")
    assert "EMP-0002" not in set(out.employee_id)
    rej = led.rejected()
    assert set(rej.reason_code) == {"HIRE_AFTER_EXIT"} and len(rej) == (emp.employee_id == "EMP-0002").sum()


def test_swapped_leave_dates_are_fixed_and_flagged(tmp_path, validator):
    cfg = make_cfg(tmp_path)
    run(cfg, validator)
    lv = pd.read_csv(cfg.clean_dir / "leave.csv")
    assert lv.dates_swapped_fixed.sum() == 2 and (lv.end_date >= lv.start_date).all()


def test_pandera_catches_negative_salary(tmp_path):
    pytest.importorskip("pandera")
    from pulseiq_etl.validate import PipelineValidationError, validate_all
    cfg = make_cfg(tmp_path)
    set_cutoff(cfg.cutoff_date)
    clean = {}
    run(cfg, rules_validator)
    for t in ("employee", "salary", "payroll", "attendance", "leave"):
        clean[t] = pd.read_csv(cfg.clean_dir / f"{t}.csv", parse_dates=[
            c for c in pd.read_csv(cfg.clean_dir / f"{t}.csv", nrows=0).columns if c.endswith(("_date", "valid_from", "valid_to"))])
    clean["payroll"].loc[0, "gross_pay"] = -1
    with pytest.raises(PipelineValidationError):
        validate_all(clean)
