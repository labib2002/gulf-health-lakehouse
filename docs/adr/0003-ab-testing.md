# ADR 0003 — A/B testing analysis

- **Status:** Accepted
- **Phase:** 2 — A/B testing
- **Date:** 2026-04-08

## Context

The generator produces a notification experiment (template A vs B) with a binary
next-day-engagement outcome and a per-user assignment. We need an analysis that
is **transparent** (the statistic visible, not a black-box library call),
includes confidence intervals and a **sample-size / power** justification, and is
honest about what the result does and doesn't show.

## Decision

- **`analysis/ab_test/stats.py`** implements each statistic from its formula:
  - **two-proportion z-test** (primary — the outcome is binary): pooled SE under
    H0 for the test statistic, unpooled SE for the CI.
  - **Welch t-test** on the 0/1 arrays as a cross-check (unequal-variance safe).
  - **`required_sample_size`** and **`achieved_power`** via the standard normal
    approximation.
  scipy is used **only** for `norm`/`t` CDF and ppf (the distribution itself),
  never to "run the test".
- **`ab_test.py`** loads the experiment parquet, runs both tests, computes
  required-n and achieved-power, renders two plots
  (`docs/img/ab_engagement_by_variant.png`, `ab_power_curve.png`), and writes
  `results.md`.
- **`results.md`** states H0/H1, the observed table, both test results, the
  power/sample-size verdict, and an explicit threats-to-validity section.
- **Tests** check the z value against a hand computation, the Welch path against
  `scipy.stats.ttest_ind(equal_var=False)`, and power/sample-size consistency
  (e.g. n from `required_sample_size` yields ~target power).

## Honest result

With 500 synthetic users (~249/group) the observed lift is small and **not
significant** (z≈0.41, p≈0.68). The true generator lift is 3 pp, but detecting
3 pp at 80% power needs **≈2,787 users/group** — so achieved power is only ~13%.
This is deliberately an **underpowered** study: the headline lesson is that a
non-significant result here is *inconclusive*, not proof of no effect.

## Alternatives considered

- **`statsmodels.proportions_ztest`** — rejected as the primary path; it hides
  the statistic. We keep the math explicit (and only validate against scipy).
- **Chi-squared test** — equivalent to the two-sided z-test for a 2×2 here; the
  z-test gives a signed effect + CI, which is more useful.
- **Bayesian A/B (Beta-Binomial)** — interesting but heavier than the brief; the
  frequentist test plus an explicit power analysis covers the interview ground.
- **Inflating the synthetic user count just to get significance** — rejected;
  that would be dishonest. The underpowered result is the teaching point.

## Consequences

- The analysis is reproducible (`make ab-test`) and defensible line by line.
- The power curve makes the sample-size argument visual and concrete.
- Re-running requires the full generated data (the 5-user sample is too small);
  documented in `results.md`.

## Interview check

**What is the null hypothesis?**
H0: the new template B has no effect — engagement_rate(B) = engagement_rate(A).
H1 (two-sided): the rates differ. We reject H0 only if p < alpha (0.05).

**Why that sample size?**
Power analysis: to detect the designed 3 pp absolute lift at alpha=0.05 with 80%
power, the two-proportion formula gives ≈2,787 users per group. The synthetic
universe only has 500 users, so the live study is underpowered (~13% power) — we
report that explicitly rather than over-claiming.

**What would have invalidated the result?**
Peeking/optional stopping (inflates false positives), sample-ratio mismatch
(broken randomization), contamination/leakage (a user seeing both variants or the
outcome window overlapping assignment), and novelty effects (a transient spike a
"next-day" window can't distinguish from a durable lift). And above all here:
being underpowered, which makes a null result inconclusive.
