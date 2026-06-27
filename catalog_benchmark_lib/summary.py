from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


def parse_timer_output(output: str) -> dict[str, float]:
    current_phase = "startup"
    timings: dict[str, float] = {}
    for line in output.splitlines():
        if line.startswith(">>> PHASE: "):
            current_phase = line.removeprefix(">>> PHASE: ").strip()
            continue
        match = re.search(r"Run Time \(s\): real\s+([0-9.]+)", line)
        if match:
            timings[current_phase] = timings.get(current_phase, 0.0) + float(match.group(1))
    return timings


def csv_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened = []
    for row in rows:
        base = {
            key: value
            for key, value in row.items()
            if key not in {"timings", "http_groups", "http_phase_groups"}
        }
        base["http_groups"] = json.dumps(row.get("http_groups", {}), sort_keys=True)
        base["http_phase_groups"] = json.dumps(row.get("http_phase_groups", {}), sort_keys=True)
        timings = row.get("timings") or {"": ""}
        for phase, seconds in timings.items():
            flattened.append({**base, "phase": phase, "duckdb_wall_seconds": seconds})
    return flattened


def write_summary(rows: list[dict[str, Any]], output_dir: Path) -> None:
    json_path = output_dir / "summary.json"
    csv_path = output_dir / "summary.csv"
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True))
    csv_rows = csv_summary_rows(rows)
    if not csv_rows:
        csv_path.write_text("")
        return
    fieldnames = sorted({key for row in csv_rows for key in row})
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
