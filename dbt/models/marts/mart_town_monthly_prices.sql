with transactions as (

    select * from {{ ref('fct_resale_transactions') }}

)

-- Grain: one row per town x flat_type x month (months with no sales have no row).
-- Medians, not averages: a few very expensive flats would skew an average.
-- Medians can't be re-aggregated, so don't average these across towns or types.
select
    transaction_month,
    town,
    flat_type,
    count(*) as transaction_count,
    round(percentile_cont(0.5) within group (order by resale_price)::numeric, 0)
        as median_resale_price,
    round(percentile_cont(0.5) within group (order by price_per_sqm)::numeric, 2)
        as median_price_per_sqm

from transactions
group by transaction_month, town, flat_type
