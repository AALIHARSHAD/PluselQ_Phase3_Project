"""Orchestration: extract -> transform -> validate -> load, with a run log. Entry: python -m pulseiq_etl"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from . import __version__
from .config import Config
from .extract import MissingInputError, extract
from .load import sha256, write_table
from .rules import set_cutoff
from .transform import Ledger, transform_attendance, transform_employee, transform_leave, transform_payroll, transform_salary

log = logging.getLogger("pulseiq")
FACTS = ["employee", "salary", "payroll", "attendance", "leave"]


class RejectThresholdError(RuntimeError):
    pass


def _setup_logging(log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_dir / "etl.log")):
        h.setFormatter(fmt)
        root.addHandler(h)


def run(cfg: Config, validator=None) -> dict:
    """Run the pipeline. `validator(clean_dict)` defaults to the pandera validation."""
    started = datetime.now(timezone.utc)
    t0 = time.time()
    set_cutoff(cfg.cutoff_date)
    summary = {"run_id": started.strftime("%Y%m%dT%H%M%SZ"), "version": __version__,
               "started_at": started.isoformat(), "cutoff_date": cfg.cutoff_date,
               "output_format": cfg.output_format, "status": "RUNNING"}
    log.info("run %s started (cutoff %s)", summary["run_id"], cfg.cutoff_date)

    raw = extract(cfg.raw_dir)
    rows_in = {t: len(raw[t]) for t in FACTS}

    ledger = Ledger()
    refs = {k: raw[k] for k in ("department", "role", "leave_type")}
    emp = transform_employee(raw["employee"], refs, ledger, cfg.cutoff_date)
    pay = transform_payroll(raw["payroll"], emp, refs, ledger)
    clean = {
        "employee": emp,
        "payroll": pay,
        "salary": transform_salary(raw["salary"], pay, ledger),
        "attendance": transform_attendance(raw["attendance"], emp, refs, ledger),
        "leave": transform_leave(raw["leave"], emp, refs, ledger, cfg.cutoff_date),
    }
    rejected, corrected = ledger.rejected(), ledger.corrected()

    # Rejected/corrected rows are saved even if a later step fails, so they can be inspected.
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
    rejected.to_csv(cfg.rejected_dir / "rejected_rows.csv", index=False, lineterminator="\n")
    corrected.to_csv(cfg.rejected_dir / "corrected_rows.csv", index=False, lineterminator="\n")

    tables = {}
    for t in FACTS:
        rej_n = int((rejected["source_table"] == t).sum())
        tables[t] = {"rows_in": rows_in[t], "rows_out": len(clean[t]), "rejected": rej_n,
                     "corrected": int((corrected["source_table"] == t).sum()),
                     "reject_pct": round(100 * rej_n / max(rows_in[t], 1), 3)}
        log.info("transform %-10s in=%d out=%d rejected=%d corrected=%d", t, rows_in[t], len(clean[t]),
                 rej_n, tables[t]["corrected"])
    summary["tables"] = tables
    summary["rejected_by_reason"] = (rejected.groupby(["source_table", "reason_code"]).size()
                                     .rename("rows").reset_index().to_dict("records"))
    summary["corrected_by_reason"] = (corrected.groupby(["source_table", "reason_code"]).size()
                                      .rename("rows").reset_index().to_dict("records"))

    # Fail loudly: too many rejects means the source is broken, not "a few bad rows".
    too_many = {t: v["reject_pct"] for t, v in tables.items() if v["reject_pct"] > cfg.max_reject_pct}
    if too_many:
        raise RejectThresholdError(f"Reject rate above {cfg.max_reject_pct}%: {too_many}")

    if validator is None:
        from .validate import validate_all as validator
    validator(clean)  # raises PipelineValidationError -> nothing is written to clean/
    log.info("validate OK")

    summary["outputs"] = {}
    for t in FACTS:
        path = write_table(clean[t], cfg.clean_dir, t, cfg.output_format)
        summary["outputs"][t] = {"file": str(path), "rows": len(clean[t]), "sha256": sha256(path)}
        log.info("load %-10s -> %s (%d rows)", t, path, len(clean[t]))
    return _finish(summary, "SUCCESS", t0, cfg)


def _finish(summary, status, t0, cfg, error=None):
    summary["status"] = status
    summary["duration_s"] = round(time.time() - t0, 2)
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    if error:
        summary["error"] = error
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.log_dir / "run_log.jsonl", "a") as f:      # append-only history, one JSON line per run
        f.write(json.dumps(summary, default=str) + "\n")
    with open(cfg.log_dir / "last_run.json", "w") as f:      # human-readable latest run
        json.dump(summary, f, indent=2, default=str)
    log.info("run %s finished: %s in %.1fs", summary["run_id"], status, summary["duration_s"])
    return summary


def main(argv=None, validator=None) -> int:
    cfg = Config.from_env()
    _setup_logging(cfg.log_dir)
    t0 = time.time()
    try:
        run(cfg, validator)
        return 0
    except Exception as exc:  # any failure -> logged, non-zero exit code
        log.error("ETL FAILED: %s: %s", type(exc).__name__, exc)
        if hasattr(exc, "failures"):
            cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
            exc.failures.to_csv(cfg.rejected_dir / "validation_failures.csv", index=False)
            log.error("failing rows saved to %s", cfg.rejected_dir / "validation_failures.csv")
        started = {"run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                   "started_at": datetime.now(timezone.utc).isoformat()}
        _finish(started, "FAILED", t0, cfg, error=f"{type(exc).__name__}: {exc}")
        return 1
