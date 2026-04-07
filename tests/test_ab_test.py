"""Tests for the A/B statistics against known/independent references.

We check our hand-rolled formulas against:
* a manually computed textbook z value (and its normal-approx p-value),
* scipy's own Welch t-test (`ttest_ind(equal_var=False)`),
* internal consistency (bigger effect -> more power -> smaller required n).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats as sps

from analysis.ab_test.stats import (
    achieved_power,
    required_sample_size,
    two_proportion_ztest,
    welch_ttest,
)


def test_ztest_matches_hand_computation():
    # control 200/1000 = .20, treatment 240/1000 = .24
    r = two_proportion_ztest(200, 1000, 240, 1000)
    p_pool = 440 / 2000  # .22
    se = math.sqrt(p_pool * (1 - p_pool) * (2 / 1000))
    z_expected = 0.04 / se  # ≈ 2.157
    p_expected = 2 * (1 - sps.norm.cdf(abs(z_expected)))

    assert math.isclose(r.effect, 0.04, abs_tol=1e-9)
    assert math.isclose(r.statistic, z_expected, rel_tol=1e-9)
    assert math.isclose(r.p_value, p_expected, rel_tol=1e-9)
    assert r.ci_low < r.effect < r.ci_high


def test_ztest_zero_effect_is_not_significant():
    r = two_proportion_ztest(100, 1000, 100, 1000)
    assert abs(r.statistic) < 1e-9
    assert r.p_value > 0.99


def test_welch_matches_scipy():
    rng = np.random.default_rng(0)
    a = rng.binomial(1, 0.20, size=800)
    b = rng.binomial(1, 0.26, size=750)
    r = welch_ttest(a, b)
    sp = sps.ttest_ind(b, a, equal_var=False)  # note order: B - A
    assert math.isclose(r.statistic, sp.statistic, rel_tol=1e-9)
    assert math.isclose(r.p_value, sp.pvalue, rel_tol=1e-6)


def test_required_sample_size_known_value():
    # p=.20, MDE=.05 abs, alpha=.05, power=.80 -> ~1094/group (standard result).
    n = required_sample_size(0.20, 0.05, alpha=0.05, power=0.80)
    assert 1000 <= n <= 1200, n


def test_bigger_effect_needs_smaller_n():
    n_small = required_sample_size(0.20, 0.02)
    n_big = required_sample_size(0.20, 0.08)
    assert n_big < n_small


def test_power_increases_with_n():
    p_low = achieved_power(0.20, 0.25, n_per_group=100)
    p_high = achieved_power(0.20, 0.25, n_per_group=2000)
    assert p_high > p_low
    assert 0.0 <= p_low <= 1.0 and 0.0 <= p_high <= 1.0


def test_power_at_required_n_hits_target():
    # By construction, n from required_sample_size should give ~target power.
    p, mde = 0.20, 0.05
    n = required_sample_size(p, mde, alpha=0.05, power=0.80)
    power = achieved_power(p, p + mde, n_per_group=n, alpha=0.05)
    assert 0.78 <= power <= 0.85, power
