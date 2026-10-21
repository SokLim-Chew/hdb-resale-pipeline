-- Each month x town x flat_type must have at most one current version
-- (dbt_valid_to is NULL). Returns any key with more.
select
    transaction_month,
    town,
    flat_type,
    count(*) as current_versions
from {{ ref('snap_town_monthly_prices') }}
where dbt_valid_to is null
group by transaction_month, town, flat_type
having count(*) > 1
