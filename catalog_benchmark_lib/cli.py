from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from catalog_benchmark_lib.config import (
    load_targets,
    merged_env,
    missing_env,
    parse_benchmark_matrix,
)
from catalog_benchmark_lib.models import (
    ATTACH_VARIANTS,
    DEFAULT_SIZES,
    BenchmarkSize,
    CatalogTarget,
)
from catalog_benchmark_lib.paths import OUTPUT_ROOT
from catalog_benchmark_lib.runner import choose_minimal_passing, run_one
from catalog_benchmark_lib.summary import write_summary

DESCRIPTION = "Run raw DuckDB Iceberg REST catalog benchmarks."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--target", required=False, help="Target name from benchmarks/catalog_benchmarks.toml"
    )
    parser.add_argument(
        "--list-targets", action="store_true", help="List configured targets and exit"
    )
    parser.add_argument("--sizes", default="tiny,small", help="Comma-separated named sizes")
    parser.add_argument("--rows", help="Comma-separated explicit row counts; overrides --sizes")
    parser.add_argument(
        "--workload",
        choices=["crud", "tpch-read"],
        default="crud",
        help="Benchmark workload to run after attach",
    )
    parser.add_argument(
        "--scale-factors",
        help="Comma-separated TPC-H scale factors for --workload tpch-read",
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="4GB")
    parser.add_argument("--keep-tables", action="store_true")
    parser.add_argument(
        "--compat-only", action="store_true", help="Only run attach-option ablation variants"
    )
    parser.add_argument(
        "--locked-config",
        action="store_true",
        help="Run only the target default_variant across the requested size matrix",
    )
    parser.add_argument(
        "--profile", action="store_true", help="Enable DuckDB JSON profiling for the run"
    )
    parser.add_argument(
        "--variants", help="Comma-separated variant names; defaults to the ablation suite"
    )
    parser.add_argument("--run-id", help="Stable output directory suffix")
    return parser


def selected_variants(raw_variants: str | None):
    variant_names = (
        [name.strip() for name in raw_variants.split(",")]
        if raw_variants
        else list(ATTACH_VARIANTS)
    )
    variants = []
    for name in variant_names:
        if name not in ATTACH_VARIANTS:
            raise SystemExit(
                f"unknown variant {name!r}; valid variants: {', '.join(ATTACH_VARIANTS)}"
            )
        variants.append(ATTACH_VARIANTS[name])
    return variant_names, variants


def run_locked_config(
    args: argparse.Namespace,
    target: CatalogTarget,
    env: dict[str, str],
    output_dir: Path,
    benchmark_matrix: list[BenchmarkSize],
) -> list[dict[str, Any]]:
    if target.default_variant not in ATTACH_VARIANTS:
        raise SystemExit(
            f"target {target.name!r} default_variant {target.default_variant!r} "
            f"is not valid; valid variants: {', '.join(ATTACH_VARIANTS)}"
        )
    rows: list[dict[str, Any]] = []
    variant = ATTACH_VARIANTS[target.default_variant]
    for size in benchmark_matrix:
        for repetition in range(1, args.repetitions + 1):
            rows.append(
                run_one(
                    target,
                    env,
                    variant,
                    size,
                    repetition,
                    output_dir,
                    args.threads,
                    args.memory_limit,
                    args.keep_tables,
                    args.workload,
                    args.profile,
                )
            )
    return rows


def run_compat_then_benchmark(
    args: argparse.Namespace,
    target: CatalogTarget,
    env: dict[str, str],
    output_dir: Path,
    benchmark_matrix: list[BenchmarkSize],
) -> list[dict[str, Any]]:
    _, variants = selected_variants(args.variants)
    rows: list[dict[str, Any]] = []
    tiny = BenchmarkSize("tiny", DEFAULT_SIZES["tiny"])
    for variant in variants:
        rows.append(
            run_one(
                target,
                env,
                variant,
                tiny,
                1,
                output_dir,
                args.threads,
                args.memory_limit,
                args.keep_tables,
                "crud",
                args.profile,
            )
        )

    minimal = choose_minimal_passing(rows)
    if minimal is not None and not args.compat_only:
        for size in benchmark_matrix:
            for repetition in range(1, args.repetitions + 1):
                rows.append(
                    run_one(
                        target,
                        env,
                        minimal,
                        size,
                        repetition,
                        output_dir,
                        args.threads,
                        args.memory_limit,
                        args.keep_tables,
                        args.workload,
                        args.profile,
                    )
                )
    return rows


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = merged_env()
    targets = load_targets(env)

    if args.list_targets:
        for target in targets.values():
            print(f"{target.name}: {target.description}")
        return 0
    if not args.target:
        raise SystemExit("--target is required unless --list-targets is used")
    if args.target not in targets:
        valid = ", ".join(sorted(targets))
        raise SystemExit(f"unknown target {args.target!r}; valid targets: {valid}")

    target = targets[args.target]
    try:
        benchmark_matrix = parse_benchmark_matrix(
            args.workload, args.sizes, args.rows, args.scale_factors
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    missing = missing_env(target, env)
    if missing:
        raise SystemExit(f"missing required env vars for {target.name}: {', '.join(missing)}")
    if args.locked_config and (args.compat_only or args.variants):
        raise SystemExit("--locked-config cannot be combined with --compat-only or --variants")

    variant_names, _ = selected_variants(args.variants)
    run_id = args.run_id or time.strftime("%Y%m%dT%H%M%S")
    output_dir = OUTPUT_ROOT / run_id / target.name
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.locked_config:
        rows = run_locked_config(args, target, env, output_dir, benchmark_matrix)
        write_summary(rows, output_dir)
        print(output_dir)
        return 0 if all(row["passed"] for row in rows) else 1

    rows = run_compat_then_benchmark(args, target, env, output_dir, benchmark_matrix)
    write_summary(rows, output_dir)
    print(output_dir)
    compat_names = set(variant_names)
    compat_passed = any(row["passed"] for row in rows if row["variant"] in compat_names)
    benchmark_passed = all(row["passed"] for row in rows if row["variant"] == "minimal_passing")
    return 0 if compat_passed and benchmark_passed else 1
