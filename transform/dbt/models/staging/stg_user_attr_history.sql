-- Effective-dated user attribute spans (membership tier, company).
-- Raw material for the Phase 5 SCD2 dimension; here we just clean + type it.
with source as (
    select * from {{ source('raw', 'user_attr_history') }}
)

select
    cast(user_id as integer)        as user_id,
    membership_tier,
    company,
    cast(effective_from as date)    as effective_from
from source
