# ADR 0001 — Synthetic data foundation

- **Status:** Accepted
- **Phase:** 0 — Synthetic data foundation
- **Date:** 2026-03-23

## Context

The whole repo needs a realistic but **fully synthetic** health-tech dataset:
wearable activity, intraday heart rate, body-composition scans, nutrition logs,
a device dimension, and an A/B experiment. It must be:

- **reproducible** (same seed → identical bytes) so anyone can rebuild it,
- **correlated** (steps↔calories, weight trends, weekday/weekend patterns) so the
  downstream models and analyses aren't operating on noise,
- **large** (millions of rows) so the Phase 7 Spark job is genuinely justified,
- **parameterized** (any user count / date range), not hard-coded to one case.

No real user data may ever enter the repo.

## Decision

A small Python package, `data_generator/`, driven by `config.yaml`:

- **One module per entity** (`users`, `devices`, `wearables`, `body_composition`,
  `nutrition`, `experiment`) plus `utils` and a `generate` orchestrator.
- **Latent per-user traits** (baseline RHR, activity level, start weight, weight
  trend) are drawn once and then *propagated* into the facts. This is how
  correlations arise mechanically rather than being bolted on: calories are
  computed from a mass-aware Mifflin–St Jeor BMR plus an activity term derived
  from that day's steps; intraday HR is a diurnal curve whose amplitude scales
  with the day's activity; nutrition targets scale with body mass.
- **A shared daily weight trajectory** (`build_weight_trajectories`) is computed
  once and consumed by wearables (calories), body scans (sampled at cadence), and
  nutrition (intake target) so body mass stays consistent across tables.
- **Schema:** star-shaped from the start — `dim_user`, `dim_device` dimensions;
  `daily_activity`, `intraday_hr`, `body_scan`, `nutrition_log` facts;
  `user_attr_history` (effective-dated tier/company) as SCD2 raw material;
  `experiment_assignment` for the A/B test.
- **Output:** parquet **and** CSV per table. A small sample (first 5 users) is
  committed under `data/raw/sample/`; the full multi-million-row output is
  git-ignored and reproduced by the generator.

## Alternatives considered

- **A single monolithic script** — rejected; one-module-per-entity keeps each
  synthesizer readable and independently testable.
- **`np.random.seed()` global state** — rejected; global seeding makes streams
  order-dependent, so adding a table would shift another table's data. Instead
  every logical stream gets its own `numpy.random.Generator` seeded by a stable
  BLAKE2b-derived child seed `child_seed(master, table, user_id)`. Adding a new
  table never perturbs existing output.
- **Faker for the metric values** — rejected; Faker is great for names/countries
  but its values aren't correlated. Metrics come from numpy with explicit models.
- **Parquet only** — rejected; CSV is kept too because it's the friction-free
  format for a reviewer to eyeball and for `COPY` into Postgres in Phase 3.

## Consequences

- Output is deterministic and diff-stable; CI can assert on it.
- Full history ≈ **7.3M rows** (6.48M intraday HR alone) at 500 users × 18 months
  → Spark in Phase 7 is warranted, not theatre.
- The generator is the single source of truth for data; nothing downstream
  depends on committing large files.
- BLAKE2b child-seeding (not Python's salted `hash()`) is what makes determinism
  hold across machines and Python processes.

## Interview check

**Why this schema?**
A star schema mirrors how the data is actually queried: facts are events at a
grain (per user/day, per user/day/hour, per scan, per meal) and dimensions
(`dim_user`, `dim_device`) describe the entities. It maps cleanly onto dbt marts
later and onto a BigQuery star schema in Phase 5.

**How were realism / correlations modeled?**
Latent per-user traits drive the facts: steps → active minutes → calories (via
BMR + ~0.04 kcal/step), a mass-aware BMR ties calories to a shared weight
trajectory, intraday HR is a diurnal curve scaled by daily activity, and
weekends get a steps bump. A test asserts steps↔calories correlation > 0.2.

**Why parquet *and* CSV?**
Parquet is columnar/compressed — the right format for analytics, Spark, and fast
reloads. CSV is the universal, human-inspectable format and the easiest path into
Postgres (`COPY`). Keeping both costs little and serves both audiences.

**How is reproducibility guaranteed?**
A master seed in config feeds per-stream child seeds via BLAKE2b (deterministic
across processes/machines, unlike Python's per-process-salted `hash`). Faker is
seeded too. `test_determinism_same_seed` asserts two runs produce identical
frames; `test_different_seed_changes_data` asserts the seed actually matters.
