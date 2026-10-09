{#
    Median of a column, rounded to `decimals` places. Use inside a GROUP BY query.
    Postgres has no median(); percentile_cont(0.5) returns double precision,
    so cast back to numeric before round() can take a number of decimals.
#}
{% macro median(column_name, decimals=0) -%}
    round(percentile_cont(0.5) within group (order by {{ column_name }})::numeric, {{ decimals }})
{%- endmacro %}
