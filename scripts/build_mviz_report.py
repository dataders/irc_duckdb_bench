#!/usr/bin/env python3
"""Build an mviz dashboard from the combined engine matrix Parquet report."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
DEFAULT_PARQUET = REPORTS_DIR / "engine-matrix-all-20260626.parquet"
DEFAULT_CSV = REPORTS_DIR / "engine-matrix-all-20260626.csv"
DEFAULT_MARKDOWN = REPORTS_DIR / "engine-matrix-all-20260626-mviz.md"
DEFAULT_HTML = REPORTS_DIR / "engine-matrix-all-20260626-mviz.html"
DEFAULT_DATA_DIR = REPORTS_DIR / "mviz-data" / "engine-matrix-all-20260626"

SIZE_ORDER = ("tiny", "small", "medium", "large")
CATALOG_ORDER = ("aws_glue", "aws_s3_tables", "horizon", "polaris_remote")
ENGINE_ORDER = ("duckdb", "pyiceberg", "spark")
REMOTE_CATALOGS = ("polaris_remote", "horizon", "aws_s3_tables")

CATALOG_LABELS = {
    "aws_glue": "AWS Glue",
    "aws_s3_tables": "AWS S3 Tables",
    "horizon": "Snowflake Horizon",
    "polaris_remote": "Polaris remote",
}
ENGINE_LABELS = {
    "duckdb": "DuckDB",
    "pyiceberg": "PyIceberg",
    "spark": "Spark",
}
type MvizRef = tuple[Path, dict[str, Any]]


def ordered(values: set[str], preferred: tuple[str, ...]) -> list[str]:
    index = {value: position for position, value in enumerate(preferred)}
    return sorted(values, key=lambda value: (index.get(value, len(index)), value))


def slug(value: str) -> str:
    return value.lower().replace(" ", "-").replace("_", "-")


def relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def seconds(value: Any) -> float:
    return round(float(value or 0.0), 6)


def read_rows(parquet_path: Path) -> list[dict[str, Any]]:
    if not parquet_path.exists():
        raise SystemExit(f"Parquet input does not exist: {parquet_path}")
    rows = pq.read_table(parquet_path).to_pylist()
    return [row for row in rows if row.get("passed", True)]


def reset_data_dir(data_dir: Path) -> None:
    if not data_dir.exists():
        return
    for child in data_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def data_path(data_dir: Path, group: str, name: str, suffix: str) -> Path:
    return data_dir / group / f"{slug(name)}.{suffix}"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {column: "" if row.get(column) is None else row.get(column) for column in columns}
            )


def pivot_rows(
    rows: list[dict[str, Any]],
    *,
    x_field: str,
    series_field: str,
    series_values: list[str],
    filter_field: str,
    filter_value: str,
) -> list[dict[str, Any]]:
    by_x: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row[filter_field] != filter_value:
            continue
        x_value = str(row[x_field])
        output = by_x.setdefault(x_value, {"size": x_value})
        output[series_label(series_field, str(row[series_field]))] = seconds(row["operation_s"])

    result = []
    for size_value in ordered(set(by_x), SIZE_ORDER):
        output = by_x[size_value]
        for series_value in series_values:
            label = series_label(series_field, series_value)
            output.setdefault(label, None)
        result.append(output)
    return result


def pivot_metric_rows(
    rows: list[dict[str, Any]],
    *,
    metric_field: str,
    series_values: list[str],
    filter_field: str,
    filter_value: str,
) -> list[dict[str, Any]]:
    by_size: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row[filter_field] != filter_value:
            continue
        size = str(row["size"])
        output = by_size.setdefault(size, {"size": size})
        output[series_label("catalog", str(row["catalog"]))] = seconds(row[metric_field])

    result = []
    for size in ordered(set(by_size), SIZE_ORDER):
        output = by_size[size]
        for series_value in series_values:
            output.setdefault(series_label("catalog", series_value), None)
        result.append(output)
    return result


def series_label(field: str, value: str) -> str:
    if field == "catalog":
        return CATALOG_LABELS.get(value, value)
    if field == "engine":
        return ENGINE_LABELS.get(value, value)
    return value


def line_options(title: str, y_fields: list[str]) -> dict[str, Any]:
    return {
        "type": "line",
        "title": title,
        "x": "size",
        "y": y_fields,
        "format": "duration",
    }


def build_catalog_charts(rows: list[dict[str, Any]], data_dir: Path) -> list[MvizRef]:
    catalogs = ordered({str(row["catalog"]) for row in rows}, CATALOG_ORDER)
    engines = ordered({str(row["engine"]) for row in rows}, ENGINE_ORDER)
    y_fields = [ENGINE_LABELS.get(engine, engine) for engine in engines]
    refs = []
    for catalog in catalogs:
        data = pivot_rows(
            rows,
            x_field="size",
            series_field="engine",
            series_values=engines,
            filter_field="catalog",
            filter_value=catalog,
        )
        path = data_path(data_dir, "by-catalog", catalog, "csv")
        write_csv(path, data, ["size", *y_fields])
        refs.append((path, line_options(CATALOG_LABELS.get(catalog, catalog), y_fields)))
    return refs


def build_engine_charts(rows: list[dict[str, Any]], data_dir: Path) -> list[MvizRef]:
    engines = ordered({str(row["engine"]) for row in rows}, ENGINE_ORDER)
    catalogs = ordered({str(row["catalog"]) for row in rows}, CATALOG_ORDER)
    y_fields = [CATALOG_LABELS.get(catalog, catalog) for catalog in catalogs]
    refs = []
    for engine in engines:
        data = pivot_rows(
            rows,
            x_field="size",
            series_field="catalog",
            series_values=catalogs,
            filter_field="engine",
            filter_value=engine,
        )
        path = data_path(data_dir, "by-engine", engine, "csv")
        write_csv(path, data, ["size", *y_fields])
        refs.append((path, line_options(ENGINE_LABELS.get(engine, engine), y_fields)))
    return refs


def build_remote_charts(rows: list[dict[str, Any]], data_dir: Path) -> list[MvizRef]:
    engines = ordered({str(row["engine"]) for row in rows}, ENGINE_ORDER)
    y_fields = [CATALOG_LABELS[catalog] for catalog in REMOTE_CATALOGS]
    remote_rows = [row for row in rows if row["catalog"] in REMOTE_CATALOGS]
    refs = []
    for engine in engines:
        data = pivot_rows(
            remote_rows,
            x_field="size",
            series_field="catalog",
            series_values=list(REMOTE_CATALOGS),
            filter_field="engine",
            filter_value=engine,
        )
        path = data_path(data_dir, "remote-comparison", engine, "csv")
        write_csv(path, data, ["size", *y_fields])
        refs.append(
            (
                path,
                line_options(
                    f"{ENGINE_LABELS.get(engine, engine)}: remote catalogs",
                    y_fields,
                ),
            )
        )
    return refs


def build_http_chart(rows: list[dict[str, Any]], data_dir: Path) -> MvizRef:
    duckdb_rows = [
        {
            **row,
            "http_s": seconds(float(row.get("http_duration_ms") or 0) / 1000),
        }
        for row in rows
        if row["engine"] == "duckdb"
    ]
    catalogs = ordered({str(row["catalog"]) for row in duckdb_rows}, CATALOG_ORDER)
    y_fields = [CATALOG_LABELS.get(catalog, catalog) for catalog in catalogs]
    data = pivot_metric_rows(
        duckdb_rows,
        metric_field="http_s",
        series_values=catalogs,
        filter_field="engine",
        filter_value="duckdb",
    )
    path = data_path(data_dir, "http", "duckdb-http-seconds", "csv")
    write_csv(path, data, ["size", *y_fields])
    return path, line_options("DuckDB HTTP timing by catalog", y_fields)


def build_kpi_specs(rows: list[dict[str, Any]], data_dir: Path) -> list[Path]:
    remote_rows = [row for row in rows if row["catalog"] in REMOTE_CATALOGS]
    large_rows = [row for row in remote_rows if row["size"] == "large"]
    best_large = min(large_rows, key=lambda row: row["operation_s"])
    best_large_label = (
        f"Fastest large remote: {CATALOG_LABELS[best_large['catalog']]} / "
        f"{ENGINE_LABELS[best_large['engine']]}"
    )
    fastest_count = 0
    for size in SIZE_ORDER:
        for engine in ENGINE_ORDER:
            candidates = [
                row for row in remote_rows if row["size"] == size and row["engine"] == engine
            ]
            if (
                candidates
                and min(candidates, key=lambda row: row["operation_s"])["catalog"]
                == "polaris_remote"
            ):
                fastest_count += 1

    specs = [
        {
            "type": "big_value",
            "value": len(rows),
            "label": "Benchmark rows",
            "format": "num0",
        },
        {
            "type": "big_value",
            "value": seconds(best_large["operation_s"]),
            "label": best_large_label,
            "format": "duration",
        },
        {
            "type": "big_value",
            "value": fastest_count,
            "label": "Polaris remote wins across size/engine pairs",
            "format": "num0",
        },
        {
            "type": "big_value",
            "value": len(REMOTE_CATALOGS),
            "label": "Remote catalogs compared",
            "format": "num0",
        },
    ]

    paths = []
    for index, spec in enumerate(specs, start=1):
        path = data_dir / "kpis" / f"kpi-{index}.json"
        write_json(path, spec)
        paths.append(path)
    return paths


def remote_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (row["size"], row["engine"], row["catalog"]): seconds(row["operation_s"])
        for row in rows
        if row["catalog"] in REMOTE_CATALOGS
    }
    data = []
    for size in SIZE_ORDER:
        for engine in ENGINE_ORDER:
            values = {catalog: lookup.get((size, engine, catalog)) for catalog in REMOTE_CATALOGS}
            if any(value is None for value in values.values()):
                continue
            polaris = float(values["polaris_remote"] or 0)
            horizon = float(values["horizon"] or 0)
            s3_tables = float(values["aws_s3_tables"] or 0)
            best_catalog = min(values, key=lambda catalog: values[catalog] or float("inf"))
            data.append(
                {
                    "size": size,
                    "engine": ENGINE_LABELS[engine],
                    "fastest": CATALOG_LABELS[best_catalog],
                    "polaris_remote_s": values["polaris_remote"],
                    "horizon_s": horizon,
                    "aws_s3_tables_s": s3_tables,
                    "horizon_vs_polaris": round(horizon / polaris, 2) if polaris else None,
                    "s3_tables_vs_polaris": round(s3_tables / polaris, 2) if polaris else None,
                }
            )
    return data


def remote_table_options() -> dict[str, Any]:
    return {
        "type": "table",
        "title": "Remote catalog operation seconds and ratios",
        "columns": [
            {"id": "size", "title": "Size"},
            {"id": "engine", "title": "Engine"},
            {"id": "fastest", "title": "Fastest"},
            {"id": "polaris_remote_s", "title": "Polaris remote", "fmt": "duration"},
            {"id": "horizon_s", "title": "Horizon", "fmt": "duration"},
            {"id": "aws_s3_tables_s", "title": "AWS S3 Tables", "fmt": "duration"},
            {"id": "horizon_vs_polaris", "title": "Horizon / Polaris", "fmt": "num1"},
            {"id": "s3_tables_vs_polaris", "title": "S3 Tables / Polaris", "fmt": "num1"},
        ],
    }


def write_remote_table(rows: list[dict[str, Any]], data_dir: Path) -> MvizRef:
    path = data_path(data_dir, "remote-comparison", "remote-catalog-table", "csv")
    data = remote_table_rows(rows)
    write_csv(
        path,
        data,
        [
            "size",
            "engine",
            "fastest",
            "polaris_remote_s",
            "horizon_s",
            "aws_s3_tables_s",
            "horizon_vs_polaris",
            "s3_tables_vs_polaris",
        ],
    )
    return path, remote_table_options()


def http_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = []
    for row in sorted(
        [row for row in rows if row["engine"] == "duckdb"],
        key=lambda row: (
            SIZE_ORDER.index(row["size"]) if row["size"] in SIZE_ORDER else len(SIZE_ORDER),
            CATALOG_ORDER.index(row["catalog"])
            if row["catalog"] in CATALOG_ORDER
            else len(CATALOG_ORDER),
        ),
    ):
        operation_s = seconds(row["operation_s"])
        http_s = seconds(float(row.get("http_duration_ms") or 0) / 1000)
        data.append(
            {
                "size": row["size"],
                "catalog": CATALOG_LABELS.get(row["catalog"], row["catalog"]),
                "total_s": seconds(row["total_s"]),
                "operation_s": operation_s,
                "http_s": http_s,
                "http_requests": int(row.get("http_request_count") or 0),
            }
        )
    return data


def http_table_options() -> dict[str, Any]:
    return {
        "type": "table",
        "title": "DuckDB HTTP request timing",
        "columns": [
            {"id": "size", "title": "Size"},
            {"id": "catalog", "title": "Catalog"},
            {"id": "total_s", "title": "Total", "fmt": "duration"},
            {"id": "operation_s", "title": "Operation", "fmt": "duration"},
            {"id": "http_s", "title": "Summed HTTP", "fmt": "duration"},
            {"id": "http_requests", "title": "Requests", "fmt": "num0"},
        ],
    }


def write_http_table(rows: list[dict[str, Any]], data_dir: Path) -> MvizRef:
    path = data_path(data_dir, "http", "duckdb-http-table", "csv")
    write_csv(
        path,
        http_table_rows(rows),
        ["size", "catalog", "total_s", "operation_s", "http_s", "http_requests"],
    )
    return path, http_table_options()


def write_flat_csv(rows: list[dict[str, Any]], csv_path: Path) -> None:
    columns = [
        "size",
        "rows",
        "catalog",
        "catalog_label",
        "engine",
        "workload",
        "variant",
        "passed",
        "total_s",
        "operation_s",
        "read_s",
        "support_s",
        "http_duration_ms",
        "http_request_count",
    ]
    write_csv(csv_path, rows, columns)


def write_note(data_dir: Path) -> Path:
    path = data_dir / "notes" / "comparison-note.json"
    write_json(
        path,
        {
            "type": "note",
            "label": "Comparison note",
            "content": (
                "DuckDB rows use the CRUD workload. PyIceberg and Spark rows use "
                "create-write-read. `operation_s` excludes engine startup/setup where "
                "possible, but DuckDB still includes delete and read-after-delete work."
            ),
            "noteType": "warning",
        },
    )
    return path


def write_section_specs(data_dir: Path) -> dict[str, Path]:
    sections = {
        "catalog": (
            "Performance Across Data Sizes By Catalog",
            "Each chart fixes one catalog and compares DuckDB, PyIceberg, and Spark.",
        ),
        "engine": (
            "Performance Across Data Sizes By Query Engine",
            "Each chart fixes one query engine and compares catalogs across input sizes.",
        ),
        "http": (
            "DuckDB HTTP Timings",
            (
                "HTTP debug timings are populated for DuckDB CLI runs in this parquet. The "
                "HTTP metric is summed request duration, not wall time. PyIceberg and Spark "
                "rows do not include comparable HTTP request timing."
            ),
        ),
        "remote": (
            "Remote Catalog Comparison",
            "Focused comparison of Polaris remote, Snowflake Horizon, and AWS S3 Tables.",
        ),
    }
    paths = {}
    for name, (title, summary) in sections.items():
        path = data_dir / "sections" / f"{name}.json"
        write_json(
            path,
            {
                "type": "textarea",
                "content": f"## {title}\n\n{summary}",
            },
        )
        paths[name] = path
    return paths


def block(
    kind: str,
    path: Path,
    markdown_path: Path,
    size: str,
    options: dict[str, Any] | None = None,
) -> str:
    head = f"```{kind} size={size} file={relpath(path, markdown_path.parent)}"
    if options is None:
        return f"{head}\n```"
    return f"{head}\n{json.dumps(options, sort_keys=True)}\n```"


def write_markdown(
    *,
    markdown_path: Path,
    parquet_path: Path,
    csv_path: Path,
    data_dir: Path,
    kpis: list[Path],
    note: Path,
    sections: dict[str, Path],
    catalog_charts: list[MvizRef],
    engine_charts: list[MvizRef],
    http_chart: MvizRef,
    http_table_ref: MvizRef,
    remote_charts: list[MvizRef],
    remote_table_ref: MvizRef,
) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "title: DuckDB Iceberg Engine Matrix",
        "theme: light",
        "continuous: true",
        "---",
        "",
        block("big_value", kpis[0], markdown_path, "[4,2]"),
        block("big_value", kpis[1], markdown_path, "[4,2]"),
        block("big_value", kpis[2], markdown_path, "[4,2]"),
        block("big_value", kpis[3], markdown_path, "[4,2]"),
        "",
        block("note", note, markdown_path, "[16,2]"),
        "",
        block("textarea", sections["catalog"], markdown_path, "[16,2]"),
        "",
    ]

    for path, options in catalog_charts:
        lines.append(block("line", path, markdown_path, "[16,8]", options))
        lines.append("")

    lines.extend(
        [
            block("textarea", sections["engine"], markdown_path, "[16,2]"),
            "",
        ]
    )
    for path, options in engine_charts:
        lines.append(block("line", path, markdown_path, "[16,8]", options))
        lines.append("")

    lines.extend(
        [
            block("textarea", sections["http"], markdown_path, "[16,2]"),
            "",
            block("line", http_chart[0], markdown_path, "[16,8]", http_chart[1]),
            "",
            block("table", http_table_ref[0], markdown_path, "[16,7]", http_table_ref[1]),
            "",
        ]
    )

    lines.extend(
        [
            "---",
            "",
            block("textarea", sections["remote"], markdown_path, "[16,2]"),
            "",
        ]
    )
    for path, options in remote_charts:
        lines.append(block("line", path, markdown_path, "[16,8]", options))
        lines.append("")
    table_path, table_options = remote_table_ref
    lines.append(block("table", table_path, markdown_path, "[16,7]", table_options))
    lines.extend(
        [
            "",
            "### Source",
            "",
            f"Parquet input: `{relpath(parquet_path, ROOT)}`.",
            f"Flat CSV export: `{relpath(csv_path, ROOT)}`.",
            f"Generated mviz data: `{relpath(data_dir, ROOT)}`.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines))


def render_html(markdown_path: Path, html_path: Path) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["npx", "-y", "-q", "mviz", str(markdown_path), "-o", str(html_path)],
        check=True,
        cwd=ROOT,
    )
    html_path.write_text(
        "\n".join(line.rstrip() for line in html_path.read_text().splitlines()) + "\n"
    )


def build(
    parquet_path: Path,
    csv_path: Path,
    markdown_path: Path,
    html_path: Path,
    data_dir: Path,
    render: bool,
) -> None:
    rows = read_rows(parquet_path)
    reset_data_dir(data_dir)
    write_flat_csv(rows, csv_path)
    kpis = build_kpi_specs(rows, data_dir)
    note = write_note(data_dir)
    sections = write_section_specs(data_dir)
    catalog_charts = build_catalog_charts(rows, data_dir)
    engine_charts = build_engine_charts(rows, data_dir)
    http_chart = build_http_chart(rows, data_dir)
    http_table_ref = write_http_table(rows, data_dir)
    remote_charts = build_remote_charts(rows, data_dir)
    remote_table_ref = write_remote_table(rows, data_dir)
    write_markdown(
        markdown_path=markdown_path,
        parquet_path=parquet_path,
        csv_path=csv_path,
        data_dir=data_dir,
        kpis=kpis,
        note=note,
        sections=sections,
        catalog_charts=catalog_charts,
        engine_charts=engine_charts,
        http_chart=http_chart,
        http_table_ref=http_table_ref,
        remote_charts=remote_charts,
        remote_table_ref=remote_table_ref,
    )
    if render:
        render_html(markdown_path, html_path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--no-render", action="store_true", help="write mviz spec only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    build(
        parquet_path=args.parquet,
        csv_path=args.csv,
        markdown_path=args.markdown,
        html_path=args.html,
        data_dir=args.data_dir,
        render=not args.no_render,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
