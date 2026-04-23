-- Singular test (sample-ratio sanity): neither A/B variant should be wildly
-- imbalanced. Fails if either variant is below 35% of total assignments.
with counts as (
    select variant, count(*) as n
    from {{ ref('stg_experiment_assignment') }}
    group by variant
),
total as (
    select sum(n) as total_n from counts
)
select c.variant, c.n, t.total_n
from counts c
cross join total t
where c.n::numeric / t.total_n < 0.35
