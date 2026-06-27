---
title: DuckDB Iceberg Engine Matrix
theme: light
continuous: true
---

```big_value size=[4,2] file=mviz-data/engine-matrix-all-20260626/kpis/kpi-1.json
```
```big_value size=[4,2] file=mviz-data/engine-matrix-all-20260626/kpis/kpi-2.json
```
```big_value size=[4,2] file=mviz-data/engine-matrix-all-20260626/kpis/kpi-3.json
```
```big_value size=[4,2] file=mviz-data/engine-matrix-all-20260626/kpis/kpi-4.json
```

```note size=[16,2] file=mviz-data/engine-matrix-all-20260626/notes/comparison-note.json
```

```textarea size=[16,2] file=mviz-data/engine-matrix-all-20260626/sections/catalog.json
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/by-catalog/aws-glue.csv
{"format": "duration", "title": "AWS Glue", "type": "line", "x": "size", "y": ["DuckDB", "PyIceberg", "Spark"]}
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/by-catalog/aws-s3-tables.csv
{"format": "duration", "title": "AWS S3 Tables", "type": "line", "x": "size", "y": ["DuckDB", "PyIceberg", "Spark"]}
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/by-catalog/horizon.csv
{"format": "duration", "title": "Snowflake Horizon", "type": "line", "x": "size", "y": ["DuckDB", "PyIceberg", "Spark"]}
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/by-catalog/polaris-remote.csv
{"format": "duration", "title": "Polaris remote", "type": "line", "x": "size", "y": ["DuckDB", "PyIceberg", "Spark"]}
```

```textarea size=[16,2] file=mviz-data/engine-matrix-all-20260626/sections/engine.json
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/by-engine/duckdb.csv
{"format": "duration", "title": "DuckDB", "type": "line", "x": "size", "y": ["AWS Glue", "AWS S3 Tables", "Snowflake Horizon", "Polaris remote"]}
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/by-engine/pyiceberg.csv
{"format": "duration", "title": "PyIceberg", "type": "line", "x": "size", "y": ["AWS Glue", "AWS S3 Tables", "Snowflake Horizon", "Polaris remote"]}
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/by-engine/spark.csv
{"format": "duration", "title": "Spark", "type": "line", "x": "size", "y": ["AWS Glue", "AWS S3 Tables", "Snowflake Horizon", "Polaris remote"]}
```

```textarea size=[16,2] file=mviz-data/engine-matrix-all-20260626/sections/http.json
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/http/duckdb-http-seconds.csv
{"format": "duration", "title": "DuckDB HTTP timing by catalog", "type": "line", "x": "size", "y": ["AWS Glue", "AWS S3 Tables", "Snowflake Horizon", "Polaris remote"]}
```

```table size=[16,7] file=mviz-data/engine-matrix-all-20260626/http/duckdb-http-table.csv
{"columns": [{"id": "size", "title": "Size"}, {"id": "catalog", "title": "Catalog"}, {"fmt": "duration", "id": "total_s", "title": "Total"}, {"fmt": "duration", "id": "operation_s", "title": "Operation"}, {"fmt": "duration", "id": "http_s", "title": "Summed HTTP"}, {"fmt": "num0", "id": "http_requests", "title": "Requests"}], "title": "DuckDB HTTP request timing", "type": "table"}
```

---

```textarea size=[16,2] file=mviz-data/engine-matrix-all-20260626/sections/remote.json
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/remote-comparison/duckdb.csv
{"format": "duration", "title": "DuckDB: remote catalogs", "type": "line", "x": "size", "y": ["Polaris remote", "Snowflake Horizon", "AWS S3 Tables"]}
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/remote-comparison/pyiceberg.csv
{"format": "duration", "title": "PyIceberg: remote catalogs", "type": "line", "x": "size", "y": ["Polaris remote", "Snowflake Horizon", "AWS S3 Tables"]}
```

```line size=[16,8] file=mviz-data/engine-matrix-all-20260626/remote-comparison/spark.csv
{"format": "duration", "title": "Spark: remote catalogs", "type": "line", "x": "size", "y": ["Polaris remote", "Snowflake Horizon", "AWS S3 Tables"]}
```

```table size=[16,7] file=mviz-data/engine-matrix-all-20260626/remote-comparison/remote-catalog-table.csv
{"columns": [{"id": "size", "title": "Size"}, {"id": "engine", "title": "Engine"}, {"id": "fastest", "title": "Fastest"}, {"fmt": "duration", "id": "polaris_remote_s", "title": "Polaris remote"}, {"fmt": "duration", "id": "horizon_s", "title": "Horizon"}, {"fmt": "duration", "id": "aws_s3_tables_s", "title": "AWS S3 Tables"}, {"fmt": "num1", "id": "horizon_vs_polaris", "title": "Horizon / Polaris"}, {"fmt": "num1", "id": "s3_tables_vs_polaris", "title": "S3 Tables / Polaris"}], "title": "Remote catalog operation seconds and ratios", "type": "table"}
```

### Source

Parquet input: `reports/engine-matrix-all-20260626.parquet`.
Flat CSV export: `reports/engine-matrix-all-20260626.csv`.
Generated mviz data: `reports/mviz-data/engine-matrix-all-20260626`.
