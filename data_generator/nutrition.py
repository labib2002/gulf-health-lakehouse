"""Daily logged meals and macronutrients.

Not every user logs every day (adherence varies per user). On logged days we
draw a calorie target loosely coupled to the user's body mass and activity, then
split it into protein/carbs/fat with realistic macro ratios (4/4/9 kcal per g).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .utils import rng_for

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]


def build_nutrition(
    cfg: dict[str, Any],
    traits: dict[int, dict],
    weights_by_day: dict[int, np.ndarray],
    dates: list[date],
) -> pd.DataFrame:
    """One row per user per logged meal (multiple meals per logged day)."""
    seed = cfg["seed"]
    n_days = len(dates)
    rows = []

    for user_id, t in traits.items():
        rng = rng_for(seed, "nutrition", user_id)
        adherence = float(np.clip(rng.normal(0.6, 0.2), 0.1, 0.98))  # P(log a day)
        logs_day = rng.random(n_days) < adherence
        traj = weights_by_day[user_id]

        for d in range(n_days):
            if not logs_day[d]:
                continue
            # daily intake target ~ maintenance-ish, scaled by mass + activity
            target = 30 * traj[d] * t["activity_level"] + rng.normal(0, 150)
            target = float(np.clip(target, 1200, 4500))
            n_meals = int(rng.integers(2, 5))
            # split target across meals (Dirichlet for a realistic uneven split)
            shares = rng.dirichlet(np.ones(n_meals) * 2.0)
            chosen_meals = rng.choice(MEAL_TYPES, size=n_meals, replace=False)
            for m in range(n_meals):
                kcal = float(round(target * shares[m]))
                # macro ratio: protein 0.25-0.35, fat 0.20-0.35, carbs the rest
                p_ratio = rng.uniform(0.20, 0.35)
                f_ratio = rng.uniform(0.20, 0.35)
                c_ratio = max(0.1, 1 - p_ratio - f_ratio)
                protein_g = round(kcal * p_ratio / 4.0, 1)
                fat_g = round(kcal * f_ratio / 9.0, 1)
                carbs_g = round(kcal * c_ratio / 4.0, 1)
                rows.append(
                    {
                        "user_id": user_id,
                        "log_date": dates[d],
                        "meal_type": str(chosen_meals[m]),
                        "calories": kcal,
                        "protein_g": protein_g,
                        "carbs_g": carbs_g,
                        "fat_g": fat_g,
                    }
                )

    return pd.DataFrame(rows)
