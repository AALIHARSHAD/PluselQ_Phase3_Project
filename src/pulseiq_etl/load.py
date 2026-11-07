"""LOAD (for now): write clean tables to files. Task 2 will replace this with warehouse upserts.

Repeatable by design: output is sorted deterministically, written to a temp file, then atomically
renamed over the old file. Same input -> byte-identical files; running twice just rewrites them.
"""
import hashlib
import os
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_table(df: pd.DataFrame, directory: Path, name: str, fmt: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"{name}.{fmt}"
    tmp = directory / f".{name}.{fmt}.tmp"
    if fmt == "parquet":
        df.to_parquet(tmp, index=False, engine="pyarrow", compression="snappy")
    else:
        df.to_csv(tmp, index=False, date_format="%Y-%m-%d", lineterminator="\n")
    os.replace(tmp, final)  # atomic on the same filesystem
    return final
