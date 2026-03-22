"""Daily wearable activity + an intraday heart-rate series.

Correlations modeled
--------------------
* steps  -> active minutes -> calories (more movement burns more)
* weekday vs weekend activity patterns (weekends slightly more steps)
* resting HR drifts around the user's latent baseline, lower on active days
* intraday HR: a smooth diurnal curve around RHR, scaled by the day's activity

The daily table is one row per user/day; the intraday table is one row per
user/day/hour (24x bigger) — together they push the dataset into the millions
of rows, which is what justifies the Spark job in Phase 7.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .utils import date_range, rng_for


# Hour-of-day activity shape (sums to ~1): low overnight, peaks morning/evening.
_HOURLY_SHAPE = np.array(
    [0.005, 0.004, 0.003, 0.003, 0.004, 0.012, 0.035, 0.065,
     0.070, 0.060, 0.055, 0.058, 0.060, 0.052, 0.050, 0.055,
     0.060, 0.075, 0.080, 0.060, 0.040, 0.025, 0.012, 0.007]
)


def _bmr(sex: str, weight: float, height: float, age: int) -> float:
    """Mifflin-St Jeor basal metabolic rate (kcal/day)."""
    base = 10 * weight + 6.25 * height - 5 * age
    return base + (5 if sex == "M" else -161)


def build_wearables(
    cfg: dict[str, Any],
    traits: dict[int, dict],
    weights_by_day: dict[int, np.ndarray],
    dates: list[date],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (daily_activity_df, intraday_hr_df).

    ``weights_by_day`` maps user_id -> per-day weight (kg) so calories track the
    user's evolving body mass; it is produced once in generate.py and shared.
    """
    seed = cfg["seed"]
    n_days = len(dates)
    dows = np.array([d.weekday() for d in dates])  # 0=Mon .. 6=Sun
    weekend = dows >= 5

    daily_frames = []
    intraday_frames = []

    for user_id, t in traits.items():
        rng = rng_for(seed, "wearables", user_id)
        wd = weights_by_day[user_id]

        # --- steps: lognormal-ish around an activity-scaled mean, +weekend bump ---
        mean_steps = 7000 * t["activity_level"] * np.where(weekend, 1.12, 1.0)
        steps = rng.normal(mean_steps, mean_steps * 0.22)
        steps = np.clip(steps, 200, 35000).round().astype(int)

        # active minutes scale with steps (with noise); ~ steps/100 baseline
        active_min = (steps / 110.0) + rng.normal(0, 6, n_days)
        active_min = np.clip(active_min, 0, 400).round().astype(int)

        # resting HR: baseline + small daily noise, lower on more active days
        activity_z = (steps - steps.mean()) / (steps.std() + 1e-6)
        resting_hr = t["baseline_rhr"] - 1.5 * activity_z + rng.normal(0, 2.0, n_days)
        resting_hr = np.clip(resting_hr, 38, 100).round(1)

        # sleep: duration (minutes) + stage split; lighter on weekends-as-noise
        sleep_min = rng.normal(420, 45, n_days)
        sleep_min = np.clip(sleep_min, 180, 660).round().astype(int)
        deep = (sleep_min * rng.uniform(0.13, 0.23, n_days)).round().astype(int)
        rem = (sleep_min * rng.uniform(0.18, 0.27, n_days)).round().astype(int)
        light = (sleep_min - deep - rem).clip(0)

        # calories: BMR (mass-aware) + activity component (~0.04 kcal/step)
        bmr = np.array(
            [_bmr(t["sex"], wd[i], t["height_cm"], t["age"]) for i in range(n_days)]
        )
        active_kcal = steps * 0.04 + active_min * 4.0
        calories = (bmr + active_kcal + rng.normal(0, 50, n_days)).round().astype(int)

        daily_frames.append(
            pd.DataFrame(
                {
                    "user_id": user_id,
                    "activity_date": dates,
                    "device_id": 0,  # filled from user dim downstream; placeholder
                    "steps": steps,
                    "active_minutes": active_min,
                    "resting_hr": resting_hr,
                    "sleep_minutes": sleep_min,
                    "sleep_deep_minutes": deep,
                    "sleep_rem_minutes": rem,
                    "sleep_light_minutes": light,
                    "calories": calories,
                }
            )
        )

        # --- intraday HR: 24 rows/day, diurnal curve around RHR scaled by activity ---
        # peak-to-RHR headroom grows with the day's activity.
        headroom = 35 + 25 * (steps / steps.max() if steps.max() else np.zeros(n_days))
        # shape over hours, broadcast across days
        curve = _HOURLY_SHAPE / _HOURLY_SHAPE.max()  # 0..1 per hour
        # hr[day, hour] = rhr[day] + headroom[day]*curve[hour] + noise
        hr = (
            resting_hr[:, None]
            + headroom[:, None] * curve[None, :]
            + rng.normal(0, 3.0, size=(n_days, 24))
        )
        hr = np.clip(hr, 35, 200).round().astype(int)

        # flatten to long form
        day_idx = np.repeat(np.arange(n_days), 24)
        hour_idx = np.tile(np.arange(24), n_days)
        intraday_frames.append(
            pd.DataFrame(
                {
                    "user_id": user_id,
                    "activity_date": [dates[d] for d in day_idx],
                    "hour": hour_idx,
                    "heart_rate": hr.reshape(-1),
                }
            )
        )

    daily = pd.concat(daily_frames, ignore_index=True)
    intraday = pd.concat(intraday_frames, ignore_index=True)
    return daily, intraday
