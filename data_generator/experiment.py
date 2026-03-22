"""A/B experiment: notification template A (control) vs B (treatment).

Each user is randomly assigned a variant. The outcome is a binary next-day
engagement flag. Variant B carries a *true* absolute lift over the control's
base engagement rate (config: base_engagement, lift). This is the ground truth
the Phase 2 analysis tries to recover with a z-test / t-test — and because the
lift is real but small, it also exercises the power/sample-size discussion.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .utils import rng_for


def build_experiment(cfg: dict[str, Any], n_users: int) -> pd.DataFrame:
    """One row per user: variant assignment + observed engagement outcome."""
    seed = cfg["seed"]
    exp = cfg["experiment"]
    rng = rng_for(seed, "experiment")

    # assignment: Bernoulli(split) -> variant B
    is_b = rng.random(n_users) < exp["split"]
    base = exp["base_engagement"]
    lift = exp["lift"]
    p = base + is_b * lift  # per-user true engagement probability
    engaged = rng.random(n_users) < p

    return pd.DataFrame(
        {
            "user_id": range(1, n_users + 1),
            "experiment_name": exp["name"],
            "variant": ["B" if b else "A" for b in is_b],
            "engaged_next_day": engaged.astype(int),
        }
    )
