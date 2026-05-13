-- Singular test: a Type-2 dimension must have EXACTLY ONE current row per user.
-- Returns offending users (0 or >1 current versions) -> test fails if any.
select
    user_id,
    count(*) filter (where is_current) as current_versions
from {{ ref('dim_user_scd2') }}
group by user_id
having count(*) filter (where is_current) <> 1
