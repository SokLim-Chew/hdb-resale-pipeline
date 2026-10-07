with source as (

    select * from {{ source('raw', 'hdb_resale') }}

),

renamed as (

    select
        _id::integer as source_row_id,
        to_date(month, 'YYYY-MM') as transaction_month,
        town,
        flat_type,
        flat_model,
        block,
        street_name,

        -- '01 TO 03' -> 1 and 3; keep the original as a display label
        storey_range,
        split_part(storey_range, ' TO ', 1)::integer as storey_min,
        split_part(storey_range, ' TO ', 2)::integer as storey_max,

        floor_area_sqm::numeric as floor_area_sqm,
        lease_commence_date::integer as lease_commence_year,

        -- Handles all source formats: '61 years 04 months', '61 years',
        -- '61 years 01 month' and '61 years 0 months'
        substring(remaining_lease from '(\d+) year')::integer * 12
            + coalesce(substring(remaining_lease from '(\d+) month')::integer, 0)
            as remaining_lease_months,

        -- numeric, not integer: a few prices have decimals (e.g. 288888.88)
        resale_price::numeric as resale_price,
        round(resale_price::numeric / floor_area_sqm::numeric, 2) as price_per_sqm,

        _loaded_at

    from source

)

select * from renamed
