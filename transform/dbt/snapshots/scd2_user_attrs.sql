-- dbt snapshot: built-in SCD Type 2.
--
-- Where dim_user_scd2 *derives* history from already-effective-dated source
-- spans, a dbt snapshot *captures* history as the source table changes over
-- time. Each run, dbt compares the current source row to the latest snapshot row
-- and, on change to a tracked column, closes the old version (dbt_valid_to) and
-- opens a new one — giving you Type-2 history even when the source only carries
-- the *current* value.
--
-- Here we snapshot the CURRENT user attributes (dim_user's tier/company). On a
-- real schedule, a user upgrading free -> pro would produce a second versioned
-- row automatically.
{% snapshot scd2_user_attrs %}
{{
    config(
        target_schema='snapshots',
        unique_key='user_id',
        strategy='check',
        check_cols=['membership_tier', 'company'],
    )
}}

select
    user_id,
    membership_tier,
    company
from {{ ref('dim_user') }}

{% endsnapshot %}
