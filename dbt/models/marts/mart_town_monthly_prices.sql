with transactions as (

    select * from {{ ref('fct_resale_transactions') }}

),

towns as (

    select * from {{ ref('dim_town') }}

),

-- Grain: one row per town x flat_type x month (months with no sales have no row).
-- Medians, not averages: a few very expensive flats would skew an average.
-- Medians can't be re-aggregated, so don't average these across towns or types.
monthly as (

    select
        transaction_month,
        town,
        flat_type,
        count(*) as transaction_count,
        {{ median('resale_price') }} as median_resale_price,
        {{ median('price_per_sqm', decimals=2) }} as median_price_per_sqm

    from transactions
    group by transaction_month, town, flat_type

)

-- Region is a label for filtering only; it doesn't change the grain.
select
    monthly.transaction_month,
    monthly.town,
    towns.region,
    monthly.flat_type,
    monthly.transaction_count,
    monthly.median_resale_price,
    monthly.median_price_per_sqm

from monthly
left join towns
    on monthly.town = towns.town
