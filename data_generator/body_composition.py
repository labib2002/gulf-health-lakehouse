"""Body-composition (InBody-style) scans at a lower cadence than daily wearables.

We first build a smooth per-day *latent* weight trajectory per user (a linear
trend + small autocorrelated noise). Daily calories read from this trajectory so
body mass and energy expenditure stay consistent. Scans then sample that
trajectory at the user's cadence and derive body-fat %, muscle mass, and
visceral fat from weight + demographics.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .utils import rng_for

INBODY_DEVICE_ID = 4  # matches config devices list


def build_weight_trajectories(
    cfg: dict[str, Any], traits: dict[int, dict], n_days: int
) -> dict[int, np.ndarray]:
    """Per-user array of daily weight (kg), length n_days.

    weight[d] = start + trend*(d/30) + cumulative small noise (random walk),
    clipped to a sane band. Shared with the wearables synthesizer.
    """
    seed = cfg["seed"]
    out: dict[int, np.ndarray] = {}
    for user_id, t in traits.items():
        rng = rng_for(seed, "weight", user_id)
        trend_per_day = t["weight_trend"] / 30.0
        steps = rng.normal(0, 0.05, n_days)  # daily fluctuation (kg)
        walk = np.cumsum(steps)
        traj = t["start_weight"] + trend_per_day * np.arange(n_days) + walk
        out[user_id] = np.clip(traj, 40, 200)
    return out


def _body_fat_pct(sex: str, bmi: float, age: int, rng: np.random.Generator) -> float:
    """Deurenberg-style body-fat estimate from BMI/age/sex, plus noise."""
    sex_factor = 1 if sex == "M" else 0
    bf = 1.20 * bmi + 0.23 * age - 10.8 * sex_factor - 5.4 + rng.normal(0, 1.5)
    return float(np.clip(bf, 5, 55))


def build_body_scans(
    cfg: dict[str, Any],
    traits: dict[int, dict],
    weights_by_day: dict[int, np.ndarray],
    dates: list[date],
) -> pd.DataFrame:
    """One row per user per scan day (cadence assigned per user)."""
    seed = cfg["seed"]
    cadences = cfg["body_scan_cadences"]
    n_days = len(dates)
    rows = []

    for user_id, t in traits.items():
        rng = rng_for(seed, "bodyscan", user_id)
        cadence = int(rng.choice(cadences))
        scan_offsets = list(range(0, n_days, cadence))
        traj = weights_by_day[user_id]
        h_m = t["height_cm"] / 100.0

        for off in scan_offsets:
            weight = float(round(traj[off], 1))
            bmi = weight / (h_m**2)
            bf = round(_body_fat_pct(t["sex"], bmi, t["age"], rng), 1)
            fat_mass = weight * bf / 100.0
            # Muscle (skeletal) mass: a fraction of fat-free mass.
            ffm = weight - fat_mass
            muscle = round(ffm * rng.uniform(0.48, 0.55), 1)
            visceral = round(np.clip((bf / 5.0) + rng.normal(0, 1.0), 1, 30), 1)
            rows.append(
                {
                    "user_id": user_id,
                    "scan_date": dates[off],
                    "device_id": INBODY_DEVICE_ID,
                    "weight_kg": weight,
                    "bmi": round(bmi, 1),
                    "body_fat_pct": bf,
                    "muscle_mass_kg": muscle,
                    "visceral_fat": visceral,
                }
            )

    return pd.DataFrame(rows)
