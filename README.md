# DuckDB Iceberg REST Catalog Benchmark

Standalone benchmark harness for DuckDB's Iceberg REST catalog behavior. It runs
the DuckDB CLI directly, records DuckDB phase timing and HTTP request timing, and
compares attach-option compatibility across Lakekeeper, Polaris, and Snowflake
Horizon targets.

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

Build a static dashboard for the newest benchmark run:

```bash
uv run scripts/build_dashboard.py
```

## Development

```bash
uv run tests/test_build_dashboard.py -v
uv run tests/test_catalog_benchmark.py -v
uv run tests/test_standalone_project.py -v
uv run --group dev ruff format --check --no-cache scripts tests
uv run --group dev ruff check --no-cache scripts tests
uv run --group dev ty check scripts tests
```
