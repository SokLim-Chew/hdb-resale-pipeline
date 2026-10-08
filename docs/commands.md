# Commands

Every command used in this project, grouped by task, with what it does and why. Commands marked **(planned)** belong to upcoming phases. They're the expected commands; confirm them when that phase is built.

All commands run from the repo root unless a section says otherwise. dbt commands run from inside `dbt/`.

## Contents

- [One-time setup](#one-time-setup)
- [Warehouse (Docker)](#warehouse-docker)
- [Python environment (uv)](#python-environment-uv)
- [Ingestion](#ingestion)
- [Python tests (pytest)](#python-tests-pytest)
- [Inspecting the warehouse (psql)](#inspecting-the-warehouse-psql)
- [dbt](#dbt)
- [Git workflow](#git-workflow)
- [Troubleshooting](#troubleshooting)
- [Planned: Phases 3–7](#planned-phases-37)

---

## One-time setup

```bash
cp .env.example .env
```
Creates your local settings file. Edit `WAREHOUSE_PASSWORD` before first starting the warehouse. Use only letters, numbers, `-` and `_`: a `$` is read differently by Docker Compose and python-dotenv. `.env` is gitignored.

```bash
uv python pin 3.12
```
Writes `.python-version`, so uv always uses Python 3.12 (needed for dbt compatibility). Already committed; only needed again if the pin changes.

## Warehouse (Docker)

| Command | What it does |
|---|---|
| `docker compose up -d` | Starts the warehouse (Postgres 17, container `hdb_warehouse`) in the background (`-d` = detached). Phases 1–4 need only this. |
| `docker compose --profile airflow up -d` | Also starts Airflow and its metadata DB. UI at http://localhost:8080, no login. Phase 5 onwards. |
| `docker compose ps` | Shows which containers are running and whether they're healthy. |
| `docker compose down` | Stops containers. **Data is kept** in the Docker volumes. |
| `docker compose down -v` | Stops containers **and deletes the volumes**, wiping all warehouse and Airflow data. Only use when a reset is intended; reload data afterwards. |

## Python environment (uv)

| Command | What it does |
|---|---|
| `uv sync` | Creates or updates `.venv` to match `uv.lock` exactly. Run after cloning, pulling, or switching branches. |
| `uv add <package>` | Installs a package and records it in `pyproject.toml` and `uv.lock`. |
| `uv add --dev <package>` | Same, but as a dev dependency (needed for development/CI, not to run the pipeline), e.g. `pytest`. |
| `uv lock` | Regenerates `uv.lock` from `pyproject.toml`. Use after resolving a merge conflict in `uv.lock`, rather than editing it by hand. |
| `uv lock --check` | Fails if `uv.lock` is out of date with `pyproject.toml`. |
| `uv run <command>` | Runs a command inside the project's `.venv` without activating it. |
| `uv run python --version` | Confirms which Python the project uses (should be 3.12.x). |

Dependencies added so far:

```bash
uv add requests "psycopg[binary]" python-dotenv   # Phase 1: API calls, Postgres driver, .env loading
uv add --dev pytest                               # Phase 1: unit tests
uv add dbt-postgres                               # Phase 2: dbt Core + Postgres adapter
```

## Ingestion

```bash
uv run python ingestion/load_hdb_resale.py
```
Downloads the full dataset from data.gov.sg (paginated, about 1 minute), then replaces the contents of `raw.hdb_resale` in one transaction (`TRUNCATE` + `COPY`). Safe to re-run: the row count stays the same. The warehouse must be running.

## Python tests (pytest)

| Command | What it does |
|---|---|
| `uv run pytest` | Runs all tests in `tests/`. No network or database needed (the API is mocked). |
| `uv run pytest -v` | Verbose: lists each test with PASSED/FAILED. |
| `uv run pytest tests/test_load_hdb_resale.py::test_retries_after_rate_limit` | Runs a single test (`file::test_name`). |

## Inspecting the warehouse (psql)

```bash
docker exec -it hdb_warehouse psql -U hdb -d hdb_warehouse
```
Opens an interactive SQL session inside the warehouse container (`-it` = interactive terminal). Replace `hdb`/`hdb_warehouse` if you changed them in `.env`. Exit with `\q`.

To run a single statement without opening a session, add `-c '<SQL>'`:

```bash
docker exec -it hdb_warehouse psql -U hdb -d hdb_warehouse -c '\d raw.hdb_resale'
```
`\d <table>` describes a table's columns; `\d+ <table>` also shows each column's description, which dbt writes as Postgres comments (`persist_docs`). Other useful psql commands: `\dn` lists schemas, `\dt <schema>.*` lists tables, `\dv <schema>.*` lists views.

### Useful queries

**Check a load** (row count and load time; re-run the loader and the count must not change):
```sql
SELECT count(*), max(_loaded_at) FROM raw.hdb_resale;
```

**Profile the formats of raw text columns.** Replacing every digit with `9` reveals the distinct formats:
```sql
SELECT col, pattern, count(*) AS n, min(val) AS example
FROM (
    SELECT 'month' AS col, month AS val FROM raw.hdb_resale
    UNION ALL SELECT 'remaining_lease', remaining_lease FROM raw.hdb_resale
    UNION ALL SELECT 'floor_area_sqm', floor_area_sqm FROM raw.hdb_resale
    UNION ALL SELECT 'resale_price', resale_price FROM raw.hdb_resale
    UNION ALL SELECT 'lease_commence_date', lease_commence_date FROM raw.hdb_resale
    UNION ALL SELECT 'storey_range', storey_range FROM raw.hdb_resale
) AS v
CROSS JOIN LATERAL (SELECT regexp_replace(val, '[0-9]', '9', 'g') AS pattern) AS p
GROUP BY col, pattern
ORDER BY col, n DESC;
```

**List distinct category values** (source for `accepted_values` tests):
```sql
SELECT 'town' AS col, town AS val, count(*) FROM staging.stg_hdb_resale GROUP BY 1, 2
UNION ALL SELECT 'flat_type', flat_type, count(*) FROM staging.stg_hdb_resale GROUP BY 1, 2
UNION ALL SELECT 'flat_model', flat_model, count(*) FROM staging.stg_hdb_resale GROUP BY 1, 2
ORDER BY 1, 2;
```

**Sanity-check the staging model's parsing:**
```sql
SELECT count(*) AS total_rows,
       count(*) FILTER (WHERE remaining_lease_months IS NULL) AS unparsed_leases,
       min(remaining_lease_months), max(remaining_lease_months),
       min(transaction_month), max(transaction_month),
       min(price_per_sqm), max(price_per_sqm)
FROM staging.stg_hdb_resale;
```

**Sanity-check the fact table's derived columns:**
```sql
SELECT count(*), min(flat_age_years), max(flat_age_years),
       min(remaining_lease_years), max(remaining_lease_years)
FROM marts.fct_resale_transactions;
```

**Investigate unusually young resold flats** (see the 2026-10-08 entry in [changelog.md](changelog.md)):
```sql
SELECT flat_age_years, count(*) FROM marts.fct_resale_transactions
WHERE flat_age_years < 5 GROUP BY 1 ORDER BY 1;

SELECT street_name, block, count(*) FROM marts.fct_resale_transactions
WHERE flat_age_years <= 2 GROUP BY 1, 2 ORDER BY 3 DESC;
```

**Compare prices over time** in the aggregate mart:
```sql
SELECT town, transaction_month, transaction_count, median_resale_price, median_price_per_sqm
FROM marts.mart_town_monthly_prices
WHERE flat_type = '4 ROOM' AND town IN ('PUNGGOL', 'QUEENSTOWN')
  AND transaction_month IN ('2017-01-01', '2026-09-01')
ORDER BY town, transaction_month;
```

## dbt

Run from inside `dbt/`. dbt doesn't read `.env`, so every command goes through `uv run --env-file ../.env`, which loads `.env` for that one command. `profiles.yml` then reads the `WAREHOUSE_*` variables.

```bash
cd dbt
```

| Command | What it does |
|---|---|
| `uv run dbt --version` | Shows installed dbt Core and adapter versions. |
| `uv run --env-file ../.env dbt debug` | Validates `dbt_project.yml` and `profiles.yml` and tests the database connection. Builds nothing. |
| `uv run --env-file ../.env dbt ls --resource-type source` | Lists sources dbt has found. `dbt ls` lists project resources without running anything. |
| `uv run --env-file ../.env dbt run --select stg_hdb_resale` | Builds one model, without tests. |
| `uv run --env-file ../.env dbt build --select stg_hdb_resale` | Builds one model **and** runs its tests, including singular tests that `ref()` it. |
| `uv run --env-file ../.env dbt build --select +fct_resale_transactions` | `+` before the name: the model **and everything upstream** of it. |
| `uv run --env-file ../.env dbt build --select stg_hdb_resale+` | `+` after the name: the model **and everything downstream** of it. |
| `uv run --env-file ../.env dbt build` | Builds every model and runs every test, in dependency order. A failing test skips the models that depend on it. |
| `uv run dbt clean` | Deletes `target/` and `dbt_packages/` (the `clean-targets` in `dbt_project.yml`). |
| `uv run --env-file ../.env dbt docs generate` | Builds the docs site into `target/`: `manifest.json` (project), `catalog.json` (column types and stats from Postgres), `index.html`. |
| `uv run --env-file ../.env dbt docs serve --port 8081` | Serves the docs site and opens the browser. Stop with Ctrl+C. Port 8081 because Airflow uses 8080. The lineage graph is the icon at the bottom right. |

**Seeing the SQL dbt actually ran:** `dbt/target/run/hdb_resale/models/<folder>/<model>.sql`. The compiled `SELECT` alone is under `dbt/target/compiled/`.

## Git workflow

Never commit directly to `main`. Work on a short-lived feature branch, push, and merge through a pull request.

| Command | What it does |
|---|---|
| `git status` | Shows the branch, staged/unstaged/untracked files, and any merge in progress. |
| `git switch main && git pull` | Updates local `main` from GitHub. |
| `git switch -c <branch>` | Creates a new branch from the current one and switches to it. Start each piece of work from an up-to-date `main`. |
| `git add <paths>` | Stages files for the next commit. |
| `git restore --staged <path>` | Unstages a file without touching your edits. |
| `git diff --staged` | Shows staged changes (plain `git diff` shows unstaged ones). |
| `git diff --check` | Reports leftover conflict markers and trailing whitespace. |
| `git commit -m "<message>"` | Commits staged changes. Keep one logical change per commit. |
| `git push origin <branch>` | Pushes the branch to GitHub. |
| `git fetch origin` | Downloads remote branches without changing your files. |
| `git log --oneline origin/main..<branch>` | Commits on `<branch>` that aren't on remote `main` (two dots: in the right, not in the left). |
| `git diff --name-only HEAD...MERGE_HEAD` | During a merge: files the incoming branch changed since the branches split (three dots). |

**Open a pull request:**
```bash
gh pr create --base main --head <branch> --title "<title>" --body "<description>"
```
Then merge on GitHub using **"Create a merge commit"** (not squash, which makes `main`'s history diverge from the branch and causes conflicts later), and start the next piece of work from a fresh branch:
```bash
git switch main
git pull
git switch -c <next-branch>
```

**Resolving a merge conflict in `uv.lock`.** It's a generated file, so regenerate it instead of editing it:
```bash
git checkout --theirs uv.lock   # take the incoming branch's version
uv lock                         # regenerate from the merged pyproject.toml
uv sync
uv run pytest                   # confirm the environment still works
git diff --check                # no output = no leftover conflict markers
git add uv.lock                 # mark as resolved (plus any other resolved files)
git commit                      # completes the merge with git's prepared message
```
To cancel a merge and return to the state before it: `git merge --abort`.

## Troubleshooting

**`password authentication failed for user "hdb"`.** Find out what is listening on the warehouse port:
```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
```
- **Only a Docker process:** the warehouse volume kept the password from its first start; Postgres only applies `.env` credentials when initializing an empty volume. If losing the data is acceptable, reset and reload:
  ```bash
  docker compose down -v
  docker compose up -d
  uv run python ingestion/load_hdb_resale.py
  ```
- **A `postgres` process is listed:** a local Postgres is using the port. Set `WAREHOUSE_PORT=5433` in `.env`, then run `docker compose up -d`.

**`Committing is not possible because you have unmerged files`.** A merge is still in progress. Resolve the conflicts (see the [Git workflow](#git-workflow) section), `git add` the resolved files, then `git commit`.

---

## Planned: Phases 3–7

These are the expected commands. Confirm and move each one into the sections above once its phase is built.

### Phase 3: advanced dbt
```bash
uv run --env-file ../.env dbt seed                          # load CSVs in dbt/seeds/ (town -> region mapping)
uv run --env-file ../.env dbt snapshot                      # record SCD Type 2 history
uv run --env-file ../.env dbt build --full-refresh          # rebuild incremental models from scratch
uv run --env-file ../.env dbt test --select test_type:unit  # run only dbt unit tests
uv run --env-file ../.env dbt deps                          # install packages from packages.yml (e.g. dbt_utils)
```

### Phase 4: semantic layer (MetricFlow)
```bash
uv add dbt-metricflow
uv run --env-file ../.env mf validate-configs
uv run --env-file ../.env mf query --metrics transaction_count --group-by metric_time__month
```

### Phase 5: orchestration (Airflow)
```bash
docker compose --profile airflow up -d
docker logs -f airflow                              # follow Airflow's logs
docker exec -it airflow airflow dags list           # list DAGs Airflow has found in ./dags
docker exec -it airflow airflow dags test <dag_id>  # run a DAG once, without the scheduler
```

### Phase 6: dashboard (Streamlit)
```bash
uv add streamlit
uv run streamlit run dashboard/app.py               # opens at http://localhost:8501
```

### Phase 7: quality and CI
```bash
uv add --dev ruff
uv run ruff check .                                 # lint
uv run ruff format .                                # auto-format
gh run list                                         # recent GitHub Actions runs
gh run watch                                        # follow a running workflow
```
