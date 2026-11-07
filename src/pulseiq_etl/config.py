"""Settings come from environment variables (optionally a .env file). Defaults are safe."""
import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass


@dataclass(frozen=True)
class Config:
    raw_dir: Path
    clean_dir: Path
    rejected_dir: Path
    log_dir: Path
    output_format: str
    cutoff_date: str
    max_reject_pct: float

    @classmethod
    def from_env(cls) -> "Config":
        g = os.environ.get
        fmt = g("OUTPUT_FORMAT", "parquet").lower()
        if fmt not in ("parquet", "csv"):
            raise ValueError(f"OUTPUT_FORMAT must be parquet or csv, got {fmt!r}")
        return cls(
            raw_dir=Path(g("RAW_DIR", "data/raw")),
            clean_dir=Path(g("CLEAN_DIR", "data/clean")),
            rejected_dir=Path(g("REJECTED_DIR", "data/rejected")),
            log_dir=Path(g("LOG_DIR", "logs")),
            output_format=fmt,
            cutoff_date=g("DATA_CUTOFF_DATE", "2026-09-30"),
            max_reject_pct=float(g("MAX_REJECT_PCT", "2.0")),
        )
