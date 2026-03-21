"""Device dimension: the small, static set of wearables/scales users own."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def build_device_dim(cfg: dict[str, Any]) -> pd.DataFrame:
    """Return the device dimension table straight from config."""
    rows = [
        {
            "device_id": d["device_id"],
            "brand": d["brand"],
            "model": d["model"],
            "category": d["category"],
        }
        for d in cfg["devices"]
    ]
    return pd.DataFrame(rows)


def assign_primary_devices(cfg: dict[str, Any], rng: np.random.Generator, n_users: int) -> np.ndarray:
    """Pick each user's primary *wearable* device, weighted by popularity.

    Scales (InBody) are not "worn", so they are excluded from the primary-wearable
    draw; body-scan rows reference the InBody device explicitly elsewhere.
    """
    wearables = [d for d in cfg["devices"] if d["category"] == "wearable"]
    ids = np.array([d["device_id"] for d in wearables])
    weights = np.array([d["weight"] for d in wearables], dtype=float)
    weights /= weights.sum()
    return rng.choice(ids, size=n_users, p=weights)
