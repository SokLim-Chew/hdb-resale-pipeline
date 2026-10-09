-- One row per town that appears in the data, enriched with its region from the seed.
-- Driven by the data (not the seed), so a town missing from the seed still gets a
-- row, with a NULL region that the not_null test turns into a build error.
with towns_in_data as (

    select distinct town from {{ ref('stg_hdb_resale') }}

),

town_regions as (

    select * from {{ ref('town_regions') }}

)

select
    towns_in_data.town,
    town_regions.region

from towns_in_data
left join town_regions
    on towns_in_data.town = town_regions.town
