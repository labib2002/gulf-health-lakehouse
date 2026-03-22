"""Generate the full synthetic dataset.

Usage
-----
    python -m data_generator.generate              # full dataset to data/raw/
    python -m data_generator.generate --users 20 --months 3 --no-sample
    make generate

Outputs parquet + CSV per table into ``output_dir`` and a small committed
sample (first ``sample_users`` users) into ``sample_dir``.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from .body_composition import build_body_scans, build_weight_trajectories
from .devices import build_device_dim
from .experiment import build_experiment
from .nutrition import build_nutrition
from .users import build_users
from .utils import date_range, load_config, write_table
from .wearables import build_wearables


def generate(cfg: dict) -> dict[str, pd.DataFrame]:
    """Build every table in dependency order and return them by name."""
    dates = date_range(cfg["end_date"], cfg["history_months"])
    n_days = len(dates)

    devices = build_device_dim(cfg)
    users, user_attr_history, traits = build_users(cfg)

    # Shared latent weight trajectory drives calories + body scans + nutrition.
    weights_by_day = build_weight_trajectories(cfg, traits, n_days)

    daily_activity, intraday_hr = build_wearables(cfg, traits, weights_by_day, dates)
    # Stamp each user's primary device onto their daily rows.
    device_map = users.set_index("user_id")["primary_device_id"].to_dict()
    daily_activity["device_id"] = daily_activity["user_id"].map(device_map)

    body_scans = build_body_scans(cfg, traits, weights_by_day, dates)
    nutrition = build_nutrition(cfg, traits, weights_by_day, dates)
    experiment = build_experiment(cfg, cfg["users"])

    return {
        "dim_device": devices,
        "dim_user": users,
        "user_attr_history": user_attr_history,
        "daily_activity": daily_activity,
        "intraday_hr": intraday_hr,
        "body_scan": body_scans,
        "nutrition_log": nutrition,
        "experiment_assignment": experiment,
    }


def write_all(tables: dict[str, pd.DataFrame], cfg: dict, write_sample: bool = True) -> None:
    out_dir = Path(cfg["output_dir"])
    formats = cfg["formats"]
    total_rows = 0
    for name, df in tables.items():
        write_table(df, name, out_dir, formats)
        total_rows += len(df)
        print(f"  {name:24s} {len(df):>12,} rows")
    print(f"  {'TOTAL':24s} {total_rows:>12,} rows")

    if write_sample:
        sample_dir = Path(cfg["sample_dir"])
        sample_users = set(range(1, cfg["sample_users"] + 1))
        for name, df in tables.items():
            sample = df[df["user_id"].isin(sample_users)] if "user_id" in df.columns else df
            write_table(sample, name, sample_dir, formats)
        print(f"  sample ({cfg['sample_users']} users) -> {sample_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic health data.")
    parser.add_argument("--users", type=int, help="override user count")
    parser.add_argument("--months", type=int, help="override history months")
    parser.add_argument("--seed", type=int, help="override master seed")
    parser.add_argument("--output-dir", type=str, help="override output dir")
    parser.add_argument("--no-sample", action="store_true", help="skip writing the committed sample")
    args = parser.parse_args()

    cfg = load_config()
    if args.users:
        cfg["users"] = args.users
    if args.months:
        cfg["history_months"] = args.months
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.output_dir:
        cfg["output_dir"] = args.output_dir

    print(
        f"Generating: users={cfg['users']} months={cfg['history_months']} "
        f"seed={cfg['seed']} end={cfg['end_date']}"
    )
    t0 = time.perf_counter()
    tables = generate(cfg)
    write_all(tables, cfg, write_sample=not args.no_sample)
    print(f"Done in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
