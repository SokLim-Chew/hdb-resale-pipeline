{#
    Override dbt's default schema naming. The default prefixes custom schemas
    with the profile's schema (analytics_staging), which keeps developers apart
    in a team. As a single-developer project, use the custom schema name as-is
    (staging, marts) and fall back to the profile's schema when none is set.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
