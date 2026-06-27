from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from catalog_benchmark_lib.http_debug import (
    parse_http_debug_output,
    summarize_http_events,
    summarize_http_log,
    write_http_debug_events,
)
from catalog_benchmark_lib.models import (
    ATTACH_VARIANTS,
    AttachVariant,
    BenchmarkSize,
    CatalogTarget,
)
from catalog_benchmark_lib.redaction import redact, redacted_error
from catalog_benchmark_lib.sql import artifact_stem, render_run_sql
from catalog_benchmark_lib.summary import parse_timer_output


def duckdb_cli(env: dict[str, str]) -> Path:
    candidate = env.get("DUCKDB_CLI")
    if not candidate and env.get("DUCKDB_BUILD_DIR"):
        candidate = str(Path(env["DUCKDB_BUILD_DIR"]) / "build" / "debug" / "duckdb")
    if not candidate:
        raise SystemExit("Set DUCKDB_CLI or DUCKDB_BUILD_DIR before running benchmarks.")
    path = Path(candidate)
    if not path.exists():
        raise SystemExit(f"DuckDB CLI does not exist: {path}")
    return path


def run_duckdb(
    duckdb: Path, sql_path: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(duckdb), ":memory:"],
        input=sql_path.read_text(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, **env},
        check=False,
    )


def write_redacted(path: Path, text: str, env: dict[str, str]) -> None:
    path.write_text(redact(text, env))


def run_one(
    target: CatalogTarget,
    env: dict[str, str],
    variant: AttachVariant,
    size: BenchmarkSize,
    repetition: int,
    output_dir: Path,
    threads: int,
    memory_limit: str,
    keep_tables: bool,
    workload: str = "crud",
    profile: bool = False,
) -> dict[str, Any]:
    duckdb = duckdb_cli(env)
    sql, http_log_path = render_run_sql(
        target,
        env,
        variant,
        size,
        repetition,
        output_dir,
        threads,
        memory_limit,
        keep_tables,
        workload,
        profile,
    )
    stem = artifact_stem(target, variant, size, repetition, workload)
    sql_path = output_dir / f"{stem}.sql"
    output_path = output_dir / f"{stem}.out"
    http_debug_path = output_dir / f"http_debug_{stem}.jsonl"
    write_redacted(sql_path, sql, env)

    raw_sql_path = output_dir / f"{stem}.raw.sql"
    raw_sql_path.write_text(sql)
    result = run_duckdb(duckdb, raw_sql_path, env)
    raw_sql_path.unlink(missing_ok=True)
    write_redacted(output_path, result.stdout, env)
    if http_log_path.exists():
        write_redacted(http_log_path, http_log_path.read_text(errors="replace"), env)

    http_log_summary = summarize_http_log(http_log_path)
    http_debug_events = parse_http_debug_output(result.stdout)
    write_http_debug_events(http_debug_path, http_debug_events)
    http_summary = summarize_http_events(http_debug_events)
    http_summary["http_log_table_request_count"] = http_log_summary["http_request_count"]
    http_summary["http_debug_path"] = http_debug_path.name
    timings = parse_timer_output(result.stdout)
    return {
        "target": target.name,
        "variant": variant.name,
        "workload": workload,
        "size": size.label,
        "rows": size.rows,
        "scale_factor": size.scale_factor,
        "repetition": repetition,
        "artifact_stem": stem,
        "passed": result.returncode == 0,
        "exit_code": result.returncode,
        "error": "" if result.returncode == 0 else redacted_error(result.stdout, env),
        "timings": timings,
        **http_summary,
    }


def choose_minimal_passing(rows: list[dict[str, Any]]) -> AttachVariant | None:
    passing = [row["variant"] for row in rows if row.get("passed")]
    if not passing:
        return None
    names = sorted(set(passing), key=lambda name: (len(ATTACH_VARIANTS[name].options), name))
    variant = ATTACH_VARIANTS[names[0]]
    return AttachVariant("minimal_passing", dict(variant.options))
