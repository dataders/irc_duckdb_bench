#!/usr/bin/env python3
"""Run raw DuckDB Iceberg REST catalog benchmarks.

The measured work is executed by the DuckDB CLI. Python expands target
configuration, writes SQL, invokes DuckDB, redacts artifacts, and summarizes
DuckDB timer/HTTP-log output.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from catalog_benchmark_lib import *  # noqa: E402,F403
from catalog_benchmark_lib import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
