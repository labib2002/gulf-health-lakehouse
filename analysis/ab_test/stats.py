"""Transparent statistics for the A/B test.

The point of this module is that every statistic is computed *by hand* from its
formula — scipy is used only for the reference distribution (normal/t CDF and the
inverse-CDF for critical values and power), never as a black-box "run my test"
call. Each function documents the formula it implements.

Outcome here is binary (engaged next day: 0/1), so a two-proportion **z-test** is
the natural primary test. We also include a Welch **t-test** on the same 0/1
arrays to show the parametric alternative and that, at this n, they agree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats


@dataclass
class TestResult:
    name: str
    statistic: float
    p_value: float
    ci_low: float
    ci_high: float
    effect: float  # observed difference in proportions/means (treatment - control)

    def __str__(self) -> str:
        return (
            f"{self.name}: effect={self.effect:+.4f}  stat={self.statistic:.3f}  "
            f"p={self.p_value:.4f}  95% CI=({self.ci_low:+.4f}, {self.ci_high:+.4f})"
        )


# --------------------------------------------------------------------------- #
# Two-proportion z-test
# --------------------------------------------------------------------------- #
def two_proportion_ztest(
    x_a: int, n_a: int, x_b: int, n_b: int, alpha: float = 0.05
) -> TestResult:
    """Two-sided two-proportion z-test (B - A).

    p_hat_a = x_a/n_a ; p_hat_b = x_b/n_b
    Pooled proportion (under H0: p_a == p_b):
        p_pool = (x_a + x_b) / (n_a + n_b)
    Standard error of the difference under the pooled null:
        se_pool = sqrt( p_pool*(1-p_pool) * (1/n_a + 1/n_b) )
        z = (p_hat_b - p_hat_a) / se_pool
    The confidence interval uses the *unpooled* SE (standard practice: the test
    assumes H0 for its SE, the CI estimates the actual difference):
        se_unpooled = sqrt( p_a(1-p_a)/n_a + p_b(1-p_b)/n_b )
        CI = diff ± z_{1-alpha/2} * se_unpooled
    """
    p_a = x_a / n_a
    p_b = x_b / n_b
    diff = p_b - p_a

    p_pool = (x_a + x_b) / (n_a + n_b)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    z = diff / se_pool if se_pool > 0 else 0.0

    # two-sided p-value from the standard normal
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    se_unpooled = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci_low = diff - z_crit * se_unpooled
    ci_high = diff + z_crit * se_unpooled

    return TestResult("two-proportion z-test", z, p_value, ci_low, ci_high, diff)


# --------------------------------------------------------------------------- #
# Welch's t-test (unequal variances) on the 0/1 outcome arrays
# --------------------------------------------------------------------------- #
def welch_ttest(a, b, alpha: float = 0.05) -> TestResult:
    """Welch's two-sample t-test (B - A), not assuming equal variances.

    mean diff = mean_b - mean_a
    se = sqrt( s_a^2/n_a + s_b^2/n_b )            (s^2 = sample variance, ddof=1)
    t  = diff / se
    Welch–Satterthwaite degrees of freedom:
        df = (s_a^2/n_a + s_b^2/n_b)^2 /
             [ (s_a^2/n_a)^2/(n_a-1) + (s_b^2/n_b)^2/(n_b-1) ]
    """
    import numpy as np

    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n_a, n_b = len(a), len(b)
    mean_a, mean_b = a.mean(), b.mean()
    var_a = a.var(ddof=1)
    var_b = b.var(ddof=1)
    diff = mean_b - mean_a

    se = math.sqrt(var_a / n_a + var_b / n_b)
    t = diff / se if se > 0 else 0.0

    df = (var_a / n_a + var_b / n_b) ** 2 / (
        (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
    )
    p_value = 2 * (1 - stats.t.cdf(abs(t), df))

    t_crit = stats.t.ppf(1 - alpha / 2, df)
    ci_low = diff - t_crit * se
    ci_high = diff + t_crit * se

    return TestResult("welch t-test", t, p_value, ci_low, ci_high, diff)


# --------------------------------------------------------------------------- #
# Power and required sample size for a two-proportion test
# --------------------------------------------------------------------------- #
def required_sample_size(
    p_control: float, mde: float, alpha: float = 0.05, power: float = 0.80
) -> int:
    """Per-group n to detect an absolute lift `mde` at given alpha/power (two-sided).

    Standard normal-approximation formula:
        n = ( z_{1-alpha/2}*sqrt(2*p_bar*(1-p_bar)) + z_{power}*sqrt(p1(1-p1)+p2(1-p2)) )^2
            / (p2 - p1)^2
    where p1 = p_control, p2 = p_control + mde, p_bar = (p1+p2)/2.
    """
    p1 = p_control
    p2 = p_control + mde
    p_bar = (p1 + p2) / 2
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)
    numerator = (
        z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
        + z_power * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2
    n = numerator / (p2 - p1) ** 2
    return math.ceil(n)


def achieved_power(
    p_control: float, p_treat: float, n_per_group: int, alpha: float = 0.05
) -> float:
    """Post-hoc power of a two-sided two-proportion test given the observed n.

    Uses the same normal approximation:
        se0 = sqrt(2*p_bar*(1-p_bar)/n)        (null SE)
        se1 = sqrt(p1(1-p1)/n + p2(1-p2)/n)    (alt SE)
        power = 1 - Phi( z_{1-a/2}*se0/se1 - |diff|/se1 )
    """
    p1, p2 = p_control, p_treat
    diff = abs(p2 - p1)
    p_bar = (p1 + p2) / 2
    se0 = math.sqrt(2 * p_bar * (1 - p_bar) / n_per_group)
    se1 = math.sqrt(p1 * (1 - p1) / n_per_group + p2 * (1 - p2) / n_per_group)
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    beta_z = z_alpha * se0 / se1 - diff / se1
    return float(1 - stats.norm.cdf(beta_z))
