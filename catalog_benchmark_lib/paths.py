from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_CONFIG = ROOT / "benchmarks" / "catalog_benchmarks.toml"
RUN_TEMPLATE = ROOT / "benchmarks" / "sql" / "run.sql"
OUTPUT_ROOT = ROOT / ".tmp" / "catalog_benchmarks"
