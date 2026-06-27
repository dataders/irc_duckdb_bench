# DuckDB Iceberg REST Catalog Benchmark

Standalone benchmark harness for DuckDB's Iceberg REST catalog behavior. It runs
the DuckDB CLI directly, records DuckDB phase timing and HTTP request timing, and
compares attach-option compatibility across Lakekeeper, Polaris, and Snowflake
Horizon targets.

## Current Engine Matrix Snapshot

Source: `reports/engine-matrix-all-20260626.parquet`.

### Operation Seconds By Catalog

| Size | Catalog | DuckDB | PyIceberg | Spark |
| --- | --- | --- | --- | --- |
| tiny | AWS Glue | 6.286s | 7.740s | 9.034s |
| tiny | AWS S3 Tables | 6.415s | 3.539s | 10.744s |
| tiny | Snowflake Horizon | 45.714s | 29.480s | 23.312s |
| tiny | Polaris remote | 2.389s | 1.777s | 5.270s |
| small | AWS Glue | 7.094s | 7.950s | 5.474s |
| small | AWS S3 Tables | 7.329s | 3.574s | 6.122s |
| small | Snowflake Horizon | 25.174s | 22.367s | 15.228s |
| small | Polaris remote | 2.407s | 1.564s | 2.945s |
| medium | AWS Glue | 9.672s | 9.740s | 9.340s |
| medium | AWS S3 Tables | 9.702s | 5.479s | 12.513s |
| medium | Snowflake Horizon | 24.979s | 12.693s | 19.453s |
| medium | Polaris remote | 4.146s | 2.794s | 6.160s |
| large | AWS Glue | 41.912s | 33.659s | 30.975s |
| large | AWS S3 Tables | 39.609s | 18.060s | 24.156s |
| large | Snowflake Horizon | 32.138s | 25.497s | 31.530s |
| large | Polaris remote | 20.061s | 10.439s | 8.437s |

### DuckDB HTTP Request Timing By Type

HTTP timings are populated for DuckDB CLI rows only. Values are summed request
durations; request counts are in parentheses.

#### REST config

| Size | AWS Glue | AWS S3 Tables | Snowflake Horizon | Polaris remote |
| --- | --- | --- | --- | --- |
| tiny | 0.265s (1) | 0.288s (1) | 1.093s (1) | 0.060s (1) |
| small | 0.248s (1) | 0.288s (1) | 0.412s (1) | 0.073s (1) |
| medium | 0.343s (1) | 0.327s (1) | 0.527s (1) | 0.055s (1) |
| large | 0.289s (1) | 0.326s (1) | 0.584s (1) | 0.089s (1) |

#### REST namespace

| Size | AWS Glue | AWS S3 Tables | Snowflake Horizon | Polaris remote |
| --- | --- | --- | --- | --- |
| tiny | 0.204s (2) | 0.331s (3) | 3.384s (2) | 0.099s (3) |
| small | 0.198s (2) | 0.252s (3) | 1.010s (2) | 0.100s (3) |
| medium | 0.200s (2) | 0.244s (3) | 0.937s (2) | 0.113s (3) |
| large | 0.217s (2) | 0.344s (3) | 1.147s (2) | 0.109s (3) |

#### REST create table

| Size | AWS Glue | AWS S3 Tables | Snowflake Horizon | Polaris remote |
| --- | --- | --- | --- | --- |
| tiny | 0.240s (1) | 0.618s (1) | 15.004s (1) | 0.127s (1) |
| small | 0.288s (1) | 0.971s (1) | 7.822s (1) | 0.074s (1) |
| medium | 0.352s (1) | 0.640s (1) | 6.472s (1) | 0.178s (1) |
| large | 0.307s (1) | 0.632s (1) | 5.997s (1) | 0.082s (1) |

#### REST table commit/load

| Size | AWS Glue | AWS S3 Tables | Snowflake Horizon | Polaris remote |
| --- | --- | --- | --- | --- |
| tiny | 2.889s (10) | 2.211s (10) | 27.744s (9) | 1.332s (10) |
| small | 2.688s (10) | 2.180s (10) | 17.333s (9) | 1.357s (10) |
| medium | 2.588s (10) | 2.208s (10) | 16.785s (10) | 1.338s (10) |
| large | 2.804s (10) | 2.615s (10) | 13.352s (9) | 1.579s (10) |

#### Object metadata

| Size | AWS Glue | AWS S3 Tables | Snowflake Horizon | Polaris remote |
| --- | --- | --- | --- | --- |
| tiny | 2.584s (10) | 2.701s (10) | 1.173s (11) | 0.685s (10) |
| small | 2.632s (10) | 2.588s (10) | 1.031s (10) | 0.657s (10) |
| medium | 2.638s (10) | 2.652s (10) | 0.785s (10) | 0.957s (10) |
| large | 2.942s (10) | 2.998s (10) | 0.965s (10) | 1.513s (10) |

#### Object data

| Size | AWS Glue | AWS S3 Tables | Snowflake Horizon | Polaris remote |
| --- | --- | --- | --- | --- |
| tiny | 1.067s (4) | 1.143s (4) | 0.382s (4) | 0.334s (4) |
| small | 1.821s (6) | 1.911s (6) | 0.599s (6) | 0.434s (6) |
| medium | 5.867s (17) | 6.124s (17) | 1.869s (17) | 1.891s (17) |
| large | 47.447s (140) | 45.855s (140) | 13.482s (140) | 18.971s (140) |

#### Other

| Size | AWS Glue | AWS S3 Tables | Snowflake Horizon | Polaris remote |
| --- | --- | --- | --- | --- |
| tiny | 0.000s (0) | 0.000s (0) | 0.000s (0) | 0.086s (1) |
| small | 0.000s (0) | 0.000s (0) | 0.000s (0) | 0.125s (1) |
| medium | 0.000s (0) | 0.000s (0) | 0.000s (0) | 0.103s (1) |
| large | 0.000s (0) | 0.000s (0) | 0.000s (0) | 0.076s (1) |

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

Build the flat CSV export, GitHub-readable markdown report, and mviz HTML from
the combined engine matrix Parquet file:

```bash
uv run scripts/build_mviz_report.py
```

## Development

```bash
uv run tests/test_build_dashboard.py -v
uv run tests/test_build_mviz_report.py -v
uv run tests/test_catalog_benchmark.py -v
uv run tests/test_standalone_project.py -v
uv run --group dev ruff format --check --no-cache scripts tests
uv run --group dev ruff check --no-cache scripts tests
uv run --group dev ty check scripts tests
```
