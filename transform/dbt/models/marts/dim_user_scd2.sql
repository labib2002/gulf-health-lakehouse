-- SCD Type 2 user dimension.
--
-- We turn the effective-dated attribute spans (membership_tier, company) into a
-- proper Type-2 dimension: one row per (user, attribute-version) with
-- valid_from / valid_to / is_current and a surrogate key. This is the right
-- place for SLOWLY-changing *descriptive* attributes — you can join a fact to the
-- version that was current "as of" the fact's date for correct point-in-time
-- reporting.
--
-- Contrast with weight: weight is a *measured, fast-changing* value, so it lives
-- as fact events in fct_body_scan, NOT as SCD2 attributes here. (See ADR-0006.)
--
-- valid_to of the current row is an open-ended sentinel date so range joins work.
with history as (
    select
        user_id,
        membership_tier,
        company,
        effective_from
    from {{ ref('stg_user_attr_history') }}
),

versioned as (
    select
        user_id,
        membership_tier,
        company,
        effective_from as valid_from,
        -- next span's start - 1 day = this span's end; open-ended for the latest
        coalesce(
            lead(effective_from) over (
                partition by user_id order by effective_from
            ) - interval '1 day',
            date '9999-12-31'
        ) as valid_to
    from history
)

select
    {{ dbt_utils.generate_surrogate_key(['user_id', 'valid_from']) }} as user_version_key,
    user_id,
    membership_tier,
    company,
    cast(valid_from as date) as valid_from,
    cast(valid_to as date)   as valid_to,
    (cast(valid_to as date) = date '9999-12-31') as is_current
from versioned
