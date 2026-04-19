-- Device dimension (conformed). Thin passthrough over staging; materialized as a
-- table so it can be joined cheaply by the facts and BI tools.
select
    device_id,
    brand,
    model,
    category
from {{ ref('stg_devices') }}
