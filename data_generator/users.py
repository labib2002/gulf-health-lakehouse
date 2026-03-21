"""User dimension and per-user latent traits.

Each user gets stable demographics plus *latent* fitness traits (baseline RHR,
activity level, weight trajectory) that drive correlated downstream facts. We
also generate a small history of slowly-changing attributes (membership tier,
company) with effective-dated rows — the raw material for the Phase 5 SCD2 demo.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from faker import Faker

from .devices import assign_primary_devices
from .utils import rng_for


def build_users(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, dict]]:
    """Build the user dimension, the SCD attribute-history, and a traits map.

    Returns
    -------
    users_df : current snapshot, one row per user.
    user_attr_history_df : effective-dated tier/company changes (SCD2 source).
    traits : {user_id: latent traits} consumed by the fact synthesizers.
    """
    seed = cfg["seed"]
    n = cfg["users"]
    rng = rng_for(seed, "users")

    faker = Faker()
    Faker.seed(seed)  # make Faker deterministic too

    primary_devices = assign_primary_devices(cfg, rng, n)

    users_rows = []
    history_rows = []
    traits: dict[int, dict] = {}

    end_date = date.fromisoformat(cfg["end_date"])
    history_days = cfg["history_months"] * 30
    start_date = end_date - timedelta(days=history_days - 1)

    for i in range(n):
        user_id = i + 1
        sex = rng.choice(["M", "F"])
        age = int(rng.integers(18, 65))
        height_cm = float(
            np.round(rng.normal(176 if sex == "M" else 163, 7), 1)
        )

        # Latent traits driving correlations in the facts.
        baseline_rhr = float(np.round(rng.normal(62, 7) + (age - 40) * 0.1, 1))
        activity_level = float(np.clip(rng.normal(1.0, 0.25), 0.4, 1.8))  # multiplier
        # Starting weight from a BMI draw, then a small monthly trend (kg/month).
        bmi0 = float(np.clip(rng.normal(25, 3.5), 17, 38))
        start_weight = float(np.round(bmi0 * (height_cm / 100) ** 2, 1))
        weight_trend = float(np.round(rng.normal(0.0, 0.25), 3))  # kg per 30 days

        traits[user_id] = {
            "sex": sex,
            "age": age,
            "height_cm": height_cm,
            "baseline_rhr": baseline_rhr,
            "activity_level": activity_level,
            "start_weight": start_weight,
            "weight_trend": weight_trend,
            "signup_date": start_date,
        }

        users_rows.append(
            {
                "user_id": user_id,
                "full_name": faker.name(),
                "sex": sex,
                "age": age,
                "height_cm": height_cm,
                "country": faker.country_code(),
                "primary_device_id": int(primary_devices[i]),
                "signup_date": start_date,
            }
        )

        # --- SCD2 source: 1–3 effective-dated attribute spans per user ---
        n_changes = int(rng.integers(1, 4))
        change_points = sorted(
            rng.choice(range(history_days), size=n_changes, replace=False).tolist()
        )
        change_points = [0] + [c for c in change_points if c > 0]
        for j, offset in enumerate(change_points):
            eff_from = start_date + timedelta(days=int(offset))
            # Tier tends to improve over time; company is more stable.
            tier = cfg["membership_tiers"][min(j, len(cfg["membership_tiers"]) - 1)]
            company = (
                cfg["companies"][int(rng.integers(0, len(cfg["companies"])))]
                if j == 0
                else history_rows[-1]["company"]
            )
            history_rows.append(
                {
                    "user_id": user_id,
                    "membership_tier": tier,
                    "company": company,
                    "effective_from": eff_from,
                }
            )

    users_df = pd.DataFrame(users_rows)
    history_df = pd.DataFrame(history_rows).sort_values(
        ["user_id", "effective_from"]
    ).reset_index(drop=True)
    return users_df, history_df, traits
