"""Load HDB resale transactions from data.gov.sg into raw.hdb_resale."""

import os
import time

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://data.gov.sg/api/action/datastore_search"
PAGE_SIZE = 5000
PAUSE_BETWEEN_PAGES = 1  # seconds; be polite to the API's rate limit
MAX_RETRIES = 5

SOURCE_COLUMNS = [
    "_id",
    "month",
    "town",
    "flat_type",
    "block",
    "street_name",
    "storey_range",
    "floor_area_sqm",
    "flat_model",
    "lease_commence_date",
    "remaining_lease",
    "resale_price",
]

CREATE_SCHEMA_SQL ="CREATE SCHEMA IF NOT EXISTS raw"

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


def fetch_page(session: requests.Session, resource_id: str, offset: int) -> dict:
    """Fetch one page of records, retrying with exponential backoff on HTTP 429."""
    params = {"resource_id": resource_id, "limit": PAGE_SIZE, "offset": offset}
    for attempt in range(1, MAX_RETRIES + 1):
        response = session.get(API_URL, params=params, timeout=30)
        if response.status_code == 429 and attempt < MAX_RETRIES:
            wait = 2**attempt
            print(f"Rate limited, retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        response.raise_for_status()  # any other error (or 429 on the last attempt) fails the run
        return response.json()["result"]


def fetch_all_records(resource_id: str) -> list[dict]:
    """Page through the API until an empty page comes back."""
    records: list[dict] = []
    total = None
    with requests.Session() as session:
        while True:
            result = fetch_page(session, resource_id, offset=len(records))
            page = result["records"]
            if not page:
                break
            records.extend(page)
            total = result["total"]
            print(f"Fetched {len(records):,} / {total:,} rows")
            time.sleep(PAUSE_BETWEEN_PAGES)

    if len(records) != total:
        raise RuntimeError(f"Expected {total} rows but fetched {len(records)}")
    return records


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("WAREHOUSE_HOST", "localhost"),
        port=os.getenv("WAREHOUSE_PORT", "5432"),
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
    )


def load_records(conn: psycopg.Connection, records: list[dict]) -> None:
    """Full refresh: empty the table, then bulk-load every record with COPY."""
    columns = ", ".join(SOURCE_COLUMNS)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE raw.hdb_resale")
        with cur.copy(f"COPY raw.hdb_resale ({columns}) FROM STDIN") as copy:
            for record in records:
                # record[col] raises KeyError if the API drops or renames a field
                copy.write_row([record[col] for col in SOURCE_COLUMNS])


def main() -> None:
    # Download everything before touching the database, so the transaction
    # below (and the table lock TRUNCATE takes) lasts seconds, not minutes.
    records = fetch_all_records(os.environ["HDB_RESALE_RESOURCE_ID"])

    # One transaction: leaving the `with` block commits; any error rolls back,
    # leaving the previous load intact.
    with get_connection() as conn:
        conn.execute(CREATE_SCHEMA_SQL)
        conn.execute(CREATE_TABLE_SQL)
        load_records(conn, records)
    print(f"Loaded {len(records):,} rows into raw.hdb_resale")


if __name__ == "__main__":
    main()
