"""Shared fixtures: a small, fast synthetic dataset generated once per session."""

from __future__ import annotations

import pytest

from data_generator.generate import generate
from data_generator.utils import load_config


@pytest.fixture(scope="session")
def small_cfg() -> dict:
    cfg = load_config()
    cfg["users"] = 15
    cfg["history_months"] = 2  # ~60 days -> fast
    return cfg


@pytest.fixture(scope="session")
def tables(small_cfg) -> dict:
    return generate(small_cfg)
