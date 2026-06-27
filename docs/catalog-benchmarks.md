# DuckDB Iceberg REST Catalog Benchmarks

This standalone benchmark runs the local DuckDB CLI directly against the
`iceberg` extension and compares REST-catalog behavior across local Lakekeeper,
local Apache Polaris, remote Polaris, Snowflake Horizon, AWS Glue, and Amazon
S3 Tables.

The runner records two timing views:

- DuckDB phase wall time from `.timer`.
- REST/object-store request timing from `CALL enable_logging('HTTP')`.

HTTP timing is client-observed request duration. It does not equal total DuckDB
CPU time, but it helps separate catalog round trips, object writes, and local
execution.

## Setup

On this machine, use direnv and the private dotfiles_env profile:

```bash
direnv allow
direnv exec . uv run scripts/catalog_benchmark.py --list-targets
```

The public `.envrc` loads:

```text
~/Developer/dotfiles_env/projects/irc-duckdb-bench.envrc
```

For a manual setup outside that system, create and load a local `.env`:

```bash
cp .env.example .env
set -a && source .env && set +a
```

`DUCKDB_CLI` or `DUCKDB_BUILD_DIR` must point at the local DuckDB build that has
the Iceberg REST write options you want to test.

List configured targets:

```bash
uv run scripts/catalog_benchmark.py --list-targets
```

## Local Lakekeeper

Start the bundled Lakekeeper, MinIO, and Postgres stack:

```bash
docker compose up -d
```

Required env vars:

```bash
LAKEKEEPER_S3_KEY_ID=minio-root-user
LAKEKEEPER_S3_SECRET=minio-root-password
```

Run a small benchmark:

```bash
uv run scripts/catalog_benchmark.py --target lakekeeper_local --sizes tiny,small
```

Stop with:

```bash
docker compose down -v
```

## Local Polaris

The local Polaris target follows the Apache Polaris quickstart compose stack.
That quickstart creates `quickstart_catalog` and uses RustFS-backed storage.

Start it:

```bash
scripts/start_local_polaris.sh
```

Required env vars:

```bash
POLARIS_LOCAL_ID=...
POLARIS_LOCAL_SECRET=...
```

Run:

```bash
uv run scripts/catalog_benchmark.py --target polaris_local --sizes tiny,small
```

Stop it:

```bash
scripts/stop_local_polaris.sh
```

The Polaris quickstart uses host ports `8181`, `8182`, `9000`, and `9001`.
Do not run it at the same time as the Lakekeeper stack if those ports conflict.

## Remote Polaris

Required env vars:

```bash
POLARIS_URL=...
POLARIS_WAREHOUSE=...
POLARIS_ID=...
POLARIS_SECRET=...
```

Optional:

```bash
POLARIS_OAUTH_TOKEN_URI=${POLARIS_URL}/v1/oauth/tokens
POLARIS_OAUTH_SCOPE=PRINCIPAL_ROLE:ALL
POLARIS_DEFAULT_REGION=us-east-1
```

Run:

```bash
uv run scripts/catalog_benchmark.py --target polaris_remote --sizes tiny,small,medium --repetitions 3
```

## Horizon

Required env vars:

```bash
HORIZON_ENDPOINT=...
HORIZON_WAREHOUSE=...
HORIZON_ACCESS_TOKEN=...
HORIZON_SCHEMA=AWS_CLOUD_COST
SNOWFLAKE_DEFAULT_REGION=us-east-1
```

Refresh the Horizon bearer token before running:

```bash
scripts/refresh_horizon_token.sh
```

Run:

```bash
uv run scripts/catalog_benchmark.py --target horizon --sizes tiny,small,medium --repetitions 3
```

## AWS Glue

The AWS Glue Iceberg REST endpoint uses SigV4 auth with the AWS credential
chain. The benchmark creates tables with explicit `location` properties because
Glue-backed S3 object storage tables need a table location on create.

Required env vars:

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=... # when using temporary credentials
AWS_GLUE_REST_REGION=us-west-2
AWS_GLUE_REST_ACCOUNT_ID=123456789012
AWS_GLUE_REST_SCHEMA=irc_duckdb_bench
AWS_GLUE_REST_TABLE_LOCATION_ROOT=s3://bucket/prefix
```

Run the original CRUD write benchmark:

```bash
uv run scripts/catalog_benchmark.py --target aws_glue --locked-config --sizes tiny
```

## Amazon S3 Tables

The S3 Tables Iceberg REST endpoint uses SigV4 auth with the S3 table bucket ARN
as the warehouse.

Required env vars:

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=... # when using temporary credentials
AWS_S3_TABLES_REGION=us-west-2
AWS_S3_TABLES_BUCKET_ARN=arn:aws:s3tables:us-west-2:123456789012:bucket/bucket-name
AWS_S3_TABLES_NAMESPACE=irc_duckdb_bench
```

Run the original CRUD write benchmark:

```bash
uv run scripts/catalog_benchmark.py --target aws_s3_tables --locked-config --sizes tiny
```

`scripts/configure_horizon_schema.sh` and `scripts/doctor.sh` are optional
Snowflake SQL API helpers. They need the `SNOWFLAKE_*` variables documented in
`.env.example`.

`scripts/refresh_horizon_token.sh` writes `HORIZON_ACCESS_TOKEN` back to the
configured env file. With direnv that target is
`~/Developer/dotfiles_env/projects/irc-duckdb-bench.envrc`; without direnv it
falls back to the repo `.env`.

## Data Sizes

Named defaults:

- `tiny`: 4 rows
- `small`: 10,000 rows
- `medium`: 1,000,000 rows
- `large`: 10,000,000 rows

Override with exact row counts:

```bash
uv run scripts/catalog_benchmark.py --target horizon --rows 1000,100000,1000000
```

## Attach-Option Ablation

Every run first tries these tiny-table attach variants:

- `default`
- `no_stage_create`
- `no_stage_no_purge`
- `no_multi_commit`
- `skip_create_metadata_updates`
- `stage_multi_metadata`
- `no_cleanup_on_rollback`
- `legacy_without_stage_create`
- `legacy_full_compat`

The runner records pass/fail and error text per variant, then uses the smallest
passing option set as `minimal_passing` for the larger data-size matrix.

This is the piece that answers whether Horizon still needs
`STAGE_CREATE_TABLES false` after duckdb-iceberg PR #1017.

For repeatable benchmark runs after the ablation is known, each target has a
`default_variant` in `benchmarks/catalog_benchmarks.toml`. Run only that locked
configuration across the requested sizes:

```bash
uv run scripts/catalog_benchmark.py --target horizon --locked-config --sizes tiny,small,medium
```

For the full CRUD scaling sweep, include the larger named sizes:

```bash
uv run scripts/catalog_benchmark.py \
  --target horizon \
  --locked-config \
  --sizes tiny,small,medium,large \
  --repetitions 3
```

## Read Workload

Use the TPC-H read workload when the goal is read performance as data grows.
TPC-H and TPC-DS are separate benchmark suites; this harness starts with TPC-H
because it gives a smaller, repeatable analytic read surface that is practical
across local and remote catalogs. TPC-DS is broader and useful later, but it has
many more tables and queries and is a larger expansion of the harness.

The TPC-H read workload:

- generates local TPC-H data with DuckDB `dbgen`
- materializes `lineitem`, `orders`, and `customer` into the attached Iceberg
  catalog
- runs TPC-H-style read phases `tpch_q01`, `tpch_q03`, and `tpch_q06`
- records read-only wall time separately as `read_wall_s` in the dashboard

Run a scaling sweep:

```bash
uv run scripts/catalog_benchmark.py \
  --target horizon \
  --locked-config \
  --workload tpch-read \
  --scale-factors 0.01,0.1,1 \
  --repetitions 3
```

The `rows` value in summaries for `tpch-read` estimates `lineitem` rows from the
TPC-H scale factor, so the report can order results by growing table size.

## PyIceberg Create-Write-Read Benchmark

Use `scripts/pyiceberg_create_table_benchmark.py` when the goal is to measure
the same REST catalog create/write/read path without DuckDB in the loop. The
runner reuses `benchmarks/catalog_benchmarks.toml` target definitions and
records these phases:

- load the PyIceberg REST catalog
- create the namespace when the target allows it
- drop any leftover table with the benchmark name
- create the Iceberg table
- load the created table back through the catalog
- append generated Arrow data
- scan the table back and validate row count plus id sum
- drop the table unless `--keep-tables` is set

Run the local Lakekeeper path:

```bash
docker compose up -d
direnv exec . uv run scripts/pyiceberg_create_table_benchmark.py \
  --target lakekeeper_local \
  --sizes tiny \
  --repetitions 3
```

Outputs land under:

```text
.tmp/catalog_benchmarks/<run-id>/<target>/pyiceberg-create-write-read/
```

`summary.json` keeps per-repetition phase timings. `summary.csv` flattens those
timings to one row per phase.

## Spark Create-Write-Read Benchmark

Use `scripts/spark_create_table_benchmark.py` when the goal is to measure the
same create/write/read path through single-node Spark. The runner reuses
`benchmarks/catalog_benchmarks.toml`, starts `local[2]`, writes generated rows
with Iceberg Spark, scans row count plus id sum back, and drops the table unless
`--keep-tables` is set.

Run the local Lakekeeper path:

```bash
docker compose up -d
direnv exec . uv run scripts/spark_create_table_benchmark.py \
  --target lakekeeper_local \
  --sizes tiny \
  --repetitions 3
```

Outputs land under:

```text
.tmp/catalog_benchmarks/<run-id>/<target>/spark-create-write-read/
```

`summary.json` keeps per-repetition phase timings. `summary.csv` flattens those
timings to one row per phase.

Run only the compatibility matrix:

```bash
uv run scripts/catalog_benchmark.py --target horizon --compat-only
```

Run one variant explicitly:

```bash
uv run scripts/catalog_benchmark.py --target horizon --variants default --compat-only
```

## Outputs

Outputs are ignored by git and written under:

```text
.tmp/catalog_benchmarks/<run_id>/<target>/
```

Each target directory contains:

- redacted generated SQL per run
- redacted DuckDB stdout/stderr
- redacted HTTP log CSV
- `summary.csv`
- `summary.json`

The summary includes target, variant, size, row count, repetition, phase timing,
HTTP request count, summed HTTP duration, grouped HTTP timings, and error text
for failing variants.

Build a self-contained HTML dashboard from a run directory:

```bash
uv run scripts/build_dashboard.py --run-root .tmp/catalog_benchmarks/<run_id>
```

The default output path is `reports/<run_id>-dashboard.html`. It embeds
`summary.json` plus every `http_debug_*.jsonl` record, and links back to the
redacted SQL, stdout, HTTP CSV, and JSONL artifacts.

The workload phases are:

- create table
- insert generated rows
- read back row-count checks
- delete even ids with `DELETE FROM ... WHERE id % 2 = 0`
- read back post-delete verification
- drop table cleanup

For `--workload tpch-read`, workload phases are:

- generate local TPC-H data
- load TPC-H tables into the attached catalog
- TPC-H query 1 style lineitem aggregate
- TPC-H query 3 style customer/orders/lineitem join
- TPC-H query 6 style lineitem revenue filter
- drop table cleanup

## Python Quality Gates

Run these after touching the benchmark runner or tests:

```bash
uv run --group dev ruff format --check --no-cache scripts tests catalog_benchmark_lib
uv run --group dev ruff check --no-cache scripts tests catalog_benchmark_lib
uv run --group dev ty check scripts tests catalog_benchmark_lib
uv run tests/test_catalog_benchmark.py -v
uv run tests/test_build_dashboard.py -v
uv run tests/test_pyiceberg_create_table_benchmark.py -v
uv run tests/test_spark_create_table_benchmark.py -v
uv run tests/test_standalone_project.py -v
```

Use Ruff to apply formatting:

```bash
uv run --group dev ruff format scripts tests catalog_benchmark_lib
```
