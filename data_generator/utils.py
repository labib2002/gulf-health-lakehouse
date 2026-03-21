"""Shared helpers: config loading, seeded RNG, date ranges, and writers.

Reproducibility contract
------------------------
Every random draw in the generator goes through a ``numpy.random.Generator``
seeded from the master seed in ``config.yaml``. We derive an independent,
*stable* child seed per (table, user) so that adding a new table never shifts
the random stream of an existing one. That keeps output deterministic and
diff-stable across runs and across feature additions.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML config. Environment variables override a few hot knobs."""
    import os

    cfg_path = Path(path) if path else CONFIG_PATH
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    # Allow .env-style overrides without editing the YAML.
    if os.getenv("GEN_USERS"):
        cfg["users"] = int(os.environ["GEN_USERS"])
    if os.getenv("GEN_HISTORY_MONTHS"):
        cfg["history_months"] = int(os.environ["GEN_HISTORY_MONTHS"])
    if os.getenv("GEN_SEED"):
        cfg["seed"] = int(os.environ["GEN_SEED"])
    return cfg


def child_seed(master_seed: int, *parts: Any) -> int:
    """Derive a stable 32-bit child seed from the master seed and arbitrary parts.

    Uses BLAKE2b so the mapping is deterministic across machines and Python runs
    (Python's built-in ``hash`` is salted per-process and must not be used here).
    """
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") % (2**32)


def rng_for(master_seed: int, *parts: Any) -> np.random.Generator:
    """A dedicated numpy Generator for a logical stream (e.g. a user/table)."""
    return np.random.default_rng(child_seed(master_seed, *parts))


def date_range(end: date | str, months: int) -> list[date]:
    """Inclusive list of daily dates spanning ``months`` back from ``end``.

    Approximate a month as 30 days so behaviour is independent of calendar edge
    cases — fine for synthetic history and keeps row counts predictable.
    """
    if isinstance(end, str):
        end = date.fromisoformat(end)
    n_days = months * 30
    start = end - timedelta(days=n_days - 1)
    return [start + timedelta(days=i) for i in range(n_days)]


def write_table(
    df: pd.DataFrame,
    name: str,
    output_dir: str | Path,
    formats: list[str],
) -> dict[str, Path]:
    """Write a dataframe to ``output_dir/<name>.<ext>`` for each requested format."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "parquet":
            p = out / f"{name}.parquet"
            df.to_parquet(p, index=False)
        elif fmt == "csv":
            p = out / f"{name}.csv"
            df.to_csv(p, index=False)
        else:
            raise ValueError(f"Unsupported format: {fmt!r}")
        written[fmt] = p
    return written
