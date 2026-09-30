"""Load HDB resale transactions from data.gov.sg into raw.hdb_resale."""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

CREATE_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS raw"

# Raw layer: every source field stored as TEXT, exactly as the API returns it.
# Type casting and cleaning happen later in dbt staging models.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS raw.hdb_resale (
    _id                 TEXT,
    month               TEXT,
    town                TEXT,
    flat_type           TEXT,
    block               TEXT,
    street_name         TEXT,
    storey_range        TEXT,
    floor_area_sqm      TEXT,
    flat_model          TEXT,
    lease_commence_date TEXT,
    remaining_lease     TEXT,
    resale_price        TEXT,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("WAREHOUSE_HOST", "localhost"),
        port=os.getenv("WAREHOUSE_PORT", "5432"),
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
    )


def main() -> None:
    # Leaving the `with` block commits the transaction (or rolls back on error).
    with get_connection() as conn:
        conn.execute(CREATE_SCHEMA_SQL)
        conn.execute(CREATE_TABLE_SQL)
    print("raw.hdb_resale is ready")


if __name__ == "__main__":
    main()
