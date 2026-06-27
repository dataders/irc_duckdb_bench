# DuckDB Iceberg REST Catalog Benchmark

Standalone benchmark harness for DuckDB's Iceberg REST catalog behavior. It runs
the DuckDB CLI directly, records DuckDB phase timing and HTTP request timing, and
compares attach-option compatibility across Lakekeeper, Polaris, and Snowflake
Horizon, AWS Glue, and Amazon S3 Tables targets.

## Current Findings

The latest combined report is
[`reports/engine-matrix-all-20260626.md`](reports/engine-matrix-all-20260626.md),
with a self-contained HTML view at
[`reports/engine-matrix-all-20260626.html`](reports/engine-matrix-all-20260626.html).
It combines 48 passing benchmark rows across DuckDB, PyIceberg, and Spark for
`tiny`, `small`, `medium`, and `large` sizes.

Important caveat: DuckDB uses this repo's CRUD workload, while PyIceberg and
Spark use create-write-read. The report's `operation_s` column excludes engine
startup/setup phases where possible, but DuckDB still includes delete and
read-after-delete work.

High-level results from that report:

- PyIceberg is the most frequent fastest engine: it wins 9 of 16 catalog/size
  combinations, including every Amazon S3 Tables size and most remote Polaris
  sizes.
- Spark wins 6 of 16 combinations, especially AWS Glue and some Horizon/remote
  Polaris cases.
- DuckDB wins only the tiny AWS Glue case in this mixed-workload matrix, but it
  is also the only engine here recording DuckDB HTTP request timing directly.
- Remote Polaris is the fastest catalog at large size in this run: Spark is
  fastest there at 8.437s operation time, with PyIceberg close behind at
  10.439s.
- Amazon S3 Tables is strongest with PyIceberg: 18.060s operation time at large
  size versus 24.156s for Spark and 39.609s for DuckDB.
- Horizon remains high-latency for small writes, but improves at larger sizes;
  PyIceberg is fastest at medium and large, while Spark wins tiny and small.
- The locked DuckDB variants from the run were `default` for remote Polaris,
  `stage_multi_metadata` for Horizon, `no_stage_no_purge` for AWS Glue, and
  `no_stage_create` for Amazon S3 Tables.

## Quick Start

With this machine's dotfiles setup:

```bash
direnv allow
direnv exec . uv run scripts/catalog_benchmark.py --list-targets
```

The committed `.envrc` loads the private overlay at
`~/Developer/dotfiles_env/projects/irc-duckdb-bench.envrc`.

For a manual setup outside that system:

```bash
cp .env.example .env
set -a && source .env && set +a
uv run scripts/catalog_benchmark.py --list-targets
```

Set `DUCKDB_CLI` in `.env` to the DuckDB binary you want to benchmark. The CLI
must be able to `LOAD iceberg` and `LOAD httpfs`.

Run the local Lakekeeper stack:

```bash
docker compose up -d
uv run scripts/catalog_benchmark.py --target lakekeeper_local --locked-config --sizes tiny,small
docker compose down -v
```

Run local Polaris:

```bash
scripts/start_local_polaris.sh
uv run scripts/catalog_benchmark.py --target polaris_local --locked-config --sizes tiny,small
scripts/stop_local_polaris.sh
```

Detailed target setup and output descriptions are in
[`docs/catalog-benchmarks.md`](docs/catalog-benchmarks.md).

Run the same REST catalog create/write/read path through PyIceberg instead of DuckDB:

```bash
uv run scripts/pyiceberg_create_table_benchmark.py --target lakekeeper_local --sizes tiny --repetitions 3
```

Run the same create/write/read path through single-node Spark:

```bash
uv run scripts/spark_create_table_benchmark.py --target lakekeeper_local --sizes tiny --repetitions 3
```

Run a larger CRUD scaling sweep:

```bash
uv run scripts/catalog_benchmark.py --target horizon --locked-config --sizes tiny,small,medium,large --repetitions 3
```

Run read-focused TPC-H scaling:

```bash
uv run scripts/catalog_benchmark.py --target horizon --locked-config --workload tpch-read --scale-factors 0.01,0.1,1 --repetitions 3
```

Build a static dashboard for the newest benchmark run:

```bash
uv run scripts/build_dashboard.py
```

## Development

```bash
uv run tests/test_build_dashboard.py -v
uv run tests/test_catalog_benchmark.py -v
uv run tests/test_pyiceberg_create_table_benchmark.py -v
uv run tests/test_spark_create_table_benchmark.py -v
uv run tests/test_standalone_project.py -v
uv run --group dev ruff format --check --no-cache scripts tests catalog_benchmark_lib
uv run --group dev ruff check --no-cache scripts tests catalog_benchmark_lib
uv run --group dev ty check scripts tests catalog_benchmark_lib
```
