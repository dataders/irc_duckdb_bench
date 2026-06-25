#!/usr/bin/env python3
# ruff: noqa: E501
"""Build a self-contained HTML dashboard from catalog benchmark artifacts."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / ".tmp" / "catalog_benchmarks"
REPORTS_DIR = ROOT / "reports"

WORKLOAD_PHASES = (
    "create_table",
    "insert",
    "readback",
    "delete",
    "read_after_delete",
    "cleanup",
)
SUPPORT_PHASES = (
    "startup",
    "duckdb_context",
    "secrets",
    "attach",
    "create_schema",
    "http_log",
)
PHASE_ORDER = SUPPORT_PHASES + WORKLOAD_PHASES

TARGET_LABELS = {
    "horizon": "Snowflake Horizon",
    "lakekeeper_local": "Lakekeeper local",
    "polaris_local": "Polaris local",
    "polaris_remote": "Polaris remote",
}

HTTP_GROUP_LABELS = {
    "object_data": "Object data",
    "object_metadata": "Object metadata",
    "other": "Other",
    "rest_config": "REST config",
    "rest_create_table": "REST create table",
    "rest_namespace": "REST namespace",
    "rest_table_commit_or_load": "REST table commit/load",
}


def normalize_phase(phase: str) -> str:
    """Collapse per-size/repetition timing labels into stable phase names."""
    if phase in PHASE_ORDER:
        return phase
    for prefix in WORKLOAD_PHASES:
        if phase == prefix or phase.startswith(f"{prefix} "):
            return prefix
    return phase


def default_run_root() -> Path:
    if not OUTPUT_ROOT.exists():
        raise SystemExit(f"benchmark output directory does not exist: {OUTPUT_ROOT}")
    candidates = [path for path in OUTPUT_ROOT.iterdir() if path.is_dir()]
    if not candidates:
        raise SystemExit(f"no benchmark runs found under {OUTPUT_ROOT}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def href_from(output_path: Path, artifact_path: Path) -> str:
    rel = os.path.relpath(artifact_path, output_path.parent)
    return rel.replace(os.sep, "/")


def file_size_label(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def sum_timings(timings: dict[str, Any], phases: tuple[str, ...] | None = None) -> float:
    total = 0.0
    selected = set(phases) if phases else None
    for raw_phase, duration in timings.items():
        phase = normalize_phase(raw_phase)
        if selected is None or phase in selected:
            total += float(duration)
    return total


def summarize_phase_timings(timings: dict[str, Any]) -> dict[str, float]:
    phase_timings: dict[str, float] = defaultdict(float)
    for raw_phase, duration in timings.items():
        phase_timings[normalize_phase(raw_phase)] += float(duration)
    return {phase: round(seconds, 6) for phase, seconds in phase_timings.items()}


def summarize_http_phase_groups(raw_groups: dict[str, Any]) -> dict[str, dict[str, dict[str, int]]]:
    grouped: dict[str, dict[str, dict[str, int]]] = {}
    for raw_phase, phase_groups in raw_groups.items():
        phase = normalize_phase(raw_phase)
        target_phase = grouped.setdefault(phase, {})
        for group, values in phase_groups.items():
            target_group = target_phase.setdefault(group, {"count": 0, "duration_ms": 0})
            target_group["count"] += int(values.get("count", 0))
            target_group["duration_ms"] += int(values.get("duration_ms", 0))
    return grouped


def run_key(row: dict[str, Any]) -> str:
    return (
        f"{row.get('target', 'unknown')}:{row.get('variant', 'unknown')}:"
        f"{row.get('size', 'unknown')}:r{row.get('repetition', 'unknown')}"
    )


def enrich_row(row: dict[str, Any], target_dir: Path, output_path: Path) -> dict[str, Any]:
    enriched = dict(row)
    timings = dict(enriched.get("timings", {}))
    key = run_key(enriched)
    target = str(enriched.get("target", target_dir.name))
    variant = str(enriched.get("variant", "default"))
    size = str(enriched.get("size", "unknown"))
    repetition = enriched.get("repetition", "unknown")
    base_name = f"{target}_{variant}_{size}_r{repetition}"

    enriched["run_key"] = key
    enriched["target_label"] = TARGET_LABELS.get(target, target)
    enriched["phase_timings"] = summarize_phase_timings(timings)
    enriched["total_wall_s"] = round(sum_timings(timings), 6)
    enriched["workload_wall_s"] = round(sum_timings(timings, WORKLOAD_PHASES), 6)
    enriched["support_wall_s"] = round(sum_timings(timings, SUPPORT_PHASES), 6)
    enriched["http_phase_groups"] = summarize_http_phase_groups(
        dict(enriched.get("http_phase_groups", {}))
    )

    sql_path = target_dir / f"{base_name}.sql"
    out_path = target_dir / f"{base_name}.out"
    http_csv_path = target_dir / f"http_{base_name}.csv"
    http_debug_name = enriched.get("http_debug_path")
    http_debug_path = target_dir / str(http_debug_name) if http_debug_name else None

    links = {}
    for name, path in (
        ("sql", sql_path),
        ("stdout", out_path),
        ("http_csv", http_csv_path),
        ("http_debug", http_debug_path),
        ("summary_json", target_dir / "summary.json"),
        ("summary_csv", target_dir / "summary.csv"),
    ):
        if path and path.exists():
            links[name] = href_from(output_path, path)
    enriched["artifact_links"] = links
    return enriched


def load_http_events(
    row: dict[str, Any], target_dir: Path, output_path: Path
) -> list[dict[str, Any]]:
    http_debug_name = row.get("http_debug_path")
    if not http_debug_name:
        return []

    path = target_dir / str(http_debug_name)
    if not path.exists():
        return []

    events = []
    with path.open() as handle:
        for index, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            phase = str(event.get("phase", "unknown"))
            events.append(
                {
                    "run_key": row["run_key"],
                    "target": row["target"],
                    "target_label": row["target_label"],
                    "variant": row.get("variant", ""),
                    "size": row.get("size", ""),
                    "repetition": row.get("repetition", ""),
                    "rows": row.get("rows", ""),
                    "line": index,
                    "phase": phase,
                    "normalized_phase": normalize_phase(phase),
                    "method": event.get("method", ""),
                    "status": event.get("status", ""),
                    "duration_ms": int(event.get("duration_ms", 0)),
                    "url_group": event.get("url_group", "other"),
                    "host": event.get("host", ""),
                    "path": event.get("path", ""),
                    "artifact_href": href_from(output_path, path),
                }
            )
    return events


def load_artifacts(run_root: Path, output_path: Path) -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(run_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(run_root).as_posix()
        artifacts.append(
            {
                "path": relative,
                "target": path.parent.name if path.parent != run_root else "",
                "kind": path.suffix.lstrip(".") or path.name,
                "bytes": path.stat().st_size,
                "size_label": file_size_label(path.stat().st_size),
                "href": href_from(output_path, path),
            }
        )

    report_path = REPORTS_DIR / f"{run_root.name}.md"
    if report_path.exists():
        artifacts.append(
            {
                "path": report_path.relative_to(ROOT).as_posix(),
                "target": "",
                "kind": "md",
                "bytes": report_path.stat().st_size,
                "size_label": file_size_label(report_path.stat().st_size),
                "href": href_from(output_path, report_path),
            }
        )
    return artifacts


def build_dashboard_data(run_root: Path, output_path: Path) -> dict[str, Any]:
    rows = []
    events = []
    for summary_path in sorted(run_root.glob("*/summary.json")):
        target_dir = summary_path.parent
        for raw_row in json.loads(summary_path.read_text()):
            row = enrich_row(raw_row, target_dir, output_path)
            rows.append(row)
            events.extend(load_http_events(row, target_dir, output_path))

    if not rows:
        raise SystemExit(f"no summary rows found under {run_root}")

    targets = sorted({str(row["target"]) for row in rows})
    sizes = sorted({str(row["size"]) for row in rows})
    variants = sorted({str(row["variant"]) for row in rows})
    http_groups = sorted({str(event["url_group"]) for event in events})

    return {
        "run_id": run_root.name,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_root": run_root.relative_to(ROOT).as_posix()
        if run_root.is_relative_to(ROOT)
        else str(run_root),
        "rows": rows,
        "events": events,
        "artifacts": load_artifacts(run_root, output_path),
        "targets": targets,
        "sizes": sizes,
        "variants": variants,
        "http_groups": http_groups,
        "phase_order": list(PHASE_ORDER),
        "workload_phases": list(WORKLOAD_PHASES),
        "support_phases": list(SUPPORT_PHASES),
        "target_labels": TARGET_LABELS,
        "http_group_labels": HTTP_GROUP_LABELS,
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DuckDB Catalog Benchmark Dashboard - __RUN_ID__</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fb;
      --surface: #ffffff;
      --surface-2: #f0f4f8;
      --line: #d6dde6;
      --text: #17202a;
      --muted: #5e6b7a;
      --accent: #1c7c8c;
      --accent-2: #b6572a;
      --accent-3: #4f6f52;
      --warn: #b44131;
      --good: #22734d;
      --shadow: 0 10px 24px rgba(24, 37, 56, 0.08);
      --radius: 6px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
      line-height: 1.35;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      padding: 18px 24px 14px;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1 {
      font-size: 20px;
      line-height: 1.2;
      margin: 0 0 4px;
      font-weight: 750;
    }
    .subhead {
      color: var(--muted);
      display: flex;
      flex-wrap: wrap;
      gap: 8px 16px;
      font-size: 12px;
    }
    .toolbar {
      display: grid;
      grid-template-columns: repeat(6, minmax(130px, 1fr));
      gap: 10px;
      margin-top: 14px;
      align-items: end;
    }
    label, .filter-control {
      color: var(--muted);
      display: grid;
      gap: 4px;
      font-size: 11px;
      font-weight: 650;
      text-transform: uppercase;
    }
    select, input, .multi-picker-button {
      appearance: none;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      min-height: 34px;
      padding: 7px 9px;
      width: 100%;
    }
    .multi-picker {
      position: relative;
      text-transform: none;
    }
    .multi-picker-button {
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      text-align: left;
    }
    .multi-picker-button::after {
      color: var(--muted);
      content: "▾";
      font-size: 12px;
      margin-left: 12px;
    }
    .multi-picker-menu {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      display: none;
      gap: 2px;
      left: 0;
      min-width: 100%;
      padding: 6px;
      position: absolute;
      top: calc(100% + 6px);
      z-index: 30;
    }
    .multi-picker.open .multi-picker-menu {
      display: grid;
    }
    .check-row {
      align-items: center;
      border-radius: 4px;
      color: var(--text);
      cursor: pointer;
      display: flex;
      font-size: 13px;
      font-weight: 550;
      gap: 8px;
      min-height: 32px;
      padding: 5px 7px;
      text-transform: none;
      white-space: nowrap;
    }
    .check-row:hover {
      background: var(--surface-2);
    }
    .check-row input {
      appearance: auto;
      min-height: 16px;
      padding: 0;
      width: 16px;
    }
    input::placeholder { color: #8a96a6; }
    main {
      display: grid;
      gap: 18px;
      padding: 18px 24px 28px;
    }
    .stats {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(5, minmax(130px, 1fr));
    }
    .stat, .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }
    .stat {
      min-height: 86px;
      padding: 14px;
    }
    .stat .label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .stat .value {
      font-size: 24px;
      font-weight: 760;
      margin-top: 8px;
      overflow-wrap: anywhere;
    }
    .stat .note {
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
      overflow-wrap: anywhere;
    }
    .grid-2 {
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
    .grid-3 {
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr);
    }
    .panel {
      min-width: 0;
      overflow: hidden;
    }
    .panel header {
      background: transparent;
      border: 0;
      padding: 14px 14px 4px;
      position: static;
    }
    .panel h2 {
      font-size: 14px;
      line-height: 1.2;
      margin: 0;
      font-weight: 760;
    }
    .panel .body {
      padding: 10px 14px 14px;
    }
    .chart {
      min-height: 250px;
      width: 100%;
    }
    svg {
      display: block;
      overflow: visible;
      width: 100%;
    }
    .axis, .tick, .caption, .legend {
      fill: var(--muted);
      font-size: 11px;
    }
    .bar-label {
      fill: var(--text);
      font-size: 11px;
      font-weight: 650;
    }
    .legend-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 7px 12px;
      margin-top: 8px;
    }
    .legend-item {
      align-items: center;
      color: var(--muted);
      display: inline-flex;
      font-size: 12px;
      gap: 5px;
    }
    .swatch {
      border-radius: 2px;
      display: inline-block;
      height: 10px;
      width: 10px;
    }
    .table-wrap {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      max-height: 440px;
      overflow: auto;
    }
    table {
      border-collapse: collapse;
      min-width: 100%;
      table-layout: fixed;
      width: 100%;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }
    th {
      background: var(--surface-2);
      color: #344150;
      font-size: 11px;
      font-weight: 760;
      position: sticky;
      text-transform: uppercase;
      top: 0;
      z-index: 1;
    }
    td {
      color: #263340;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    td.num, th.num { text-align: right; }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 11px;
    }
    .status-ok { color: var(--good); font-weight: 700; }
    .status-bad { color: var(--warn); font-weight: 700; }
    .links {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 9px;
    }
    .heatmap {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      display: grid;
      overflow: auto;
    }
    .heatmap-row {
      display: grid;
      grid-template-columns: 170px repeat(var(--phase-count), minmax(92px, 1fr));
      min-width: 820px;
    }
    .heatmap-cell {
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      min-height: 44px;
      padding: 6px;
    }
    .heatmap-head {
      background: var(--surface-2);
      color: #344150;
      font-size: 11px;
      font-weight: 760;
      text-transform: uppercase;
    }
    .heatmap-value {
      font-size: 12px;
      font-weight: 730;
    }
    .heatmap-note {
      color: var(--muted);
      font-size: 11px;
      margin-top: 2px;
    }
    @media (max-width: 1180px) {
      .toolbar { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .grid-2, .grid-3 { grid-template-columns: minmax(0, 1fr); }
    }
    @media (max-width: 720px) {
      header { padding: 14px; }
      main { padding: 14px; }
      .toolbar, .stats { grid-template-columns: minmax(0, 1fr); }
      .stat .value { font-size: 21px; }
      th, td { padding: 6px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>DuckDB Catalog Benchmark Dashboard</h1>
    <div class="subhead">
      <span>Run <span class="mono">__RUN_ID__</span></span>
      <span>Source <span class="mono">__RUN_ROOT__</span></span>
      <span>Generated <span class="mono">__GENERATED_AT__</span></span>
    </div>
    <div class="toolbar">
      <div class="filter-control">
        <span>Target</span>
        <div class="multi-picker" id="targetPicker">
          <button class="multi-picker-button" id="targetPickerButton" type="button"></button>
          <div class="multi-picker-menu" id="targetPickerMenu"></div>
        </div>
      </div>
      <label>Size<select id="sizeFilter"></select></label>
      <label>Phase<select id="phaseFilter"></select></label>
      <label>HTTP group<select id="groupFilter"></select></label>
      <label>Compare metric<select id="metricFilter"></select></label>
      <label>Search<input id="searchFilter" type="search" placeholder="host, path, status, run"></label>
    </div>
  </header>
  <main>
    <section class="stats" id="stats"></section>

    <section class="grid-2">
      <article class="panel">
        <header><h2>Catalog Comparison</h2></header>
        <div class="body">
          <div id="comparisonChart" class="chart"></div>
          <div id="comparisonLegend" class="legend-wrap"></div>
        </div>
      </article>
      <article class="panel">
        <header><h2>Workload Phase Wall Time</h2></header>
        <div class="body">
          <div id="phaseChart" class="chart"></div>
          <div id="phaseLegend" class="legend-wrap"></div>
        </div>
      </article>
    </section>

    <section class="grid-2">
      <article class="panel">
        <header><h2>HTTP Group Cost</h2></header>
        <div class="body">
          <div id="httpGroupChart" class="chart"></div>
          <div id="httpLegend" class="legend-wrap"></div>
        </div>
      </article>
      <article class="panel">
        <header><h2>HTTP Phase Heatmap</h2></header>
        <div class="body">
          <div id="heatmap"></div>
        </div>
      </article>
    </section>

    <section class="grid-2">
      <article class="panel">
        <header><h2>Catalog vs DuckDB Local Time</h2></header>
        <div class="body">
          <div id="attributionChart" class="chart"></div>
          <div id="attributionLegend" class="legend-wrap"></div>
        </div>
      </article>
      <article class="panel">
        <header><h2>Statement Phase Attribution</h2></header>
        <div class="body">
          <div class="table-wrap">
            <table id="attributionTable"></table>
          </div>
        </div>
      </article>
    </section>

    <section class="grid-3">
      <article class="panel">
        <header><h2>HTTP Request Log</h2></header>
        <div class="body">
          <div class="table-wrap">
            <table id="requestTable"></table>
          </div>
        </div>
      </article>
      <article class="panel">
        <header><h2>Status And Method Breakdown</h2></header>
        <div class="body">
          <div class="table-wrap">
            <table id="statusTable"></table>
          </div>
        </div>
      </article>
    </section>

    <section class="panel">
      <header><h2>Run Details</h2></header>
      <div class="body">
        <div class="table-wrap">
          <table id="runTable"></table>
        </div>
      </div>
    </section>

    <section class="panel">
      <header><h2>Artifacts</h2></header>
      <div class="body">
        <div class="table-wrap">
          <table id="artifactTable"></table>
        </div>
      </div>
    </section>
  </main>

  <script type="application/json" id="dashboard-data">__DATA__</script>
  <script>
    const dashboard = JSON.parse(document.getElementById("dashboard-data").textContent);
    const colors = [
      "#1c7c8c", "#b6572a", "#4f6f52", "#7b5aa6", "#bf8a1c", "#63758a",
      "#2f9c7a", "#9b4d5f", "#5c78c7", "#8b6f47", "#cc6f4a", "#3d8796"
    ];
    const phaseColors = {
      create_table: "#1c7c8c",
      insert: "#b6572a",
      readback: "#4f6f52",
      delete: "#7b5aa6",
      read_after_delete: "#bf8a1c",
      cleanup: "#63758a"
    };
    const attributionParts = [
      ["catalog_ms", "Catalog REST", "#1c7c8c"],
      ["object_ms", "Object store", "#b6572a"],
      ["other_http_ms", "Other HTTP", "#7b5aa6"],
      ["local_ms", "DuckDB/local", "#4f6f52"]
    ];
    const metricOptions = [
      ["workload_wall_s", "Workload wall"],
      ["total_wall_s", "Total wall"],
      ["http_duration_ms", "HTTP duration"],
      ["http_request_count", "HTTP requests"]
    ];

    const state = {
      targets: [...dashboard.targets],
      size: "all",
      phase: "all",
      group: "all",
      metric: "workload_wall_s",
      query: ""
    };

    function labelTarget(target) {
      return dashboard.target_labels[target] || target;
    }

    function labelGroup(group) {
      return dashboard.http_group_labels[group] || group;
    }

    function labelPhase(phase) {
      return phase.replaceAll("_", " ");
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function fmtNumber(value) {
      if (!Number.isFinite(value)) return "";
      return new Intl.NumberFormat("en-US").format(value);
    }

    function fmtMs(value) {
      if (!Number.isFinite(value)) return "";
      if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
      return `${Math.round(value)}ms`;
    }

    function fmtSeconds(value) {
      if (!Number.isFinite(value)) return "";
      if (value >= 10) return `${value.toFixed(2)}s`;
      if (value >= 1) return `${value.toFixed(3)}s`;
      return `${Math.round(value * 1000)}ms`;
    }

    function fmtMetric(value, metric) {
      if (metric === "http_duration_ms") return fmtMs(value);
      if (metric === "http_request_count") return fmtNumber(value);
      return fmtSeconds(value);
    }

    function fmtPercent(value) {
      if (!Number.isFinite(value)) return "";
      return `${value.toFixed(1)}%`;
    }

    function median(values) {
      const clean = values.filter(Number.isFinite).sort((a, b) => a - b);
      if (!clean.length) return NaN;
      const mid = Math.floor(clean.length / 2);
      return clean.length % 2 ? clean[mid] : (clean[mid - 1] + clean[mid]) / 2;
    }

    function sum(values) {
      return values.reduce((total, value) => total + (Number(value) || 0), 0);
    }

    function groupBy(items, keyFn) {
      const groups = new Map();
      for (const item of items) {
        const key = keyFn(item);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(item);
      }
      return groups;
    }

    function targetIsSelected(target) {
      return state.targets.includes(target);
    }

    function allTargetsSelected() {
      return state.targets.length === dashboard.targets.length;
    }

    function targetSummary() {
      if (allTargetsSelected()) return "All targets";
      if (state.targets.length === 0) return "No targets";
      if (state.targets.length === 1) return labelTarget(state.targets[0]);
      return `${state.targets.length} targets`;
    }

    function matchesQuery(row, query) {
      if (!query) return true;
      const haystack = [
        row.run_key, row.target, row.target_label, row.variant, row.size, row.status,
        row.method, row.url_group, row.host, row.path, row.phase, row.normalized_phase
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    }

    function filteredRows() {
      const query = state.query.trim().toLowerCase();
      return dashboard.rows.filter(row => {
        if (!targetIsSelected(row.target)) return false;
        if (state.size !== "all" && String(row.size) !== state.size) return false;
        if (state.phase !== "all" && !row.phase_timings[state.phase]) return false;
        if (state.group !== "all" && !(row.http_groups || {})[state.group]) return false;
        return matchesQuery(row, query);
      });
    }

    function filteredEvents() {
      const query = state.query.trim().toLowerCase();
      return dashboard.events.filter(event => {
        if (!targetIsSelected(event.target)) return false;
        if (state.size !== "all" && String(event.size) !== state.size) return false;
        if (state.phase !== "all" && event.normalized_phase !== state.phase) return false;
        if (state.group !== "all" && event.url_group !== state.group) return false;
        return matchesQuery(event, query);
      });
    }

    function populateSelect(id, entries, selected) {
      const select = document.getElementById(id);
      select.innerHTML = entries.map(([value, label]) => {
        const checked = value === selected ? " selected" : "";
        return `<option value="${escapeHtml(value)}"${checked}>${escapeHtml(label)}</option>`;
      }).join("");
    }

    function updateTargetPicker() {
      document.getElementById("targetPickerButton").textContent = targetSummary();
      document.getElementById("targetAll").checked = allTargetsSelected();
      for (const target of dashboard.targets) {
        const input = document.getElementById(`target-${target}`);
        if (input) input.checked = targetIsSelected(target);
      }
    }

    function populateTargetPicker() {
      const rows = [
        `<label class="check-row"><input id="targetAll" type="checkbox" value="__all__">All targets</label>`,
        ...dashboard.targets.map(target => `
          <label class="check-row">
            <input id="target-${escapeHtml(target)}" type="checkbox" value="${escapeHtml(target)}">
            ${escapeHtml(labelTarget(target))}
          </label>
        `)
      ].join("");
      document.getElementById("targetPickerMenu").innerHTML = rows;
      updateTargetPicker();
    }

    function populateControls() {
      populateTargetPicker();
      populateSelect("sizeFilter", [["all", "All sizes"], ...dashboard.sizes.map(s => [s, s])], state.size);
      const phases = dashboard.phase_order.filter(phase => dashboard.rows.some(row => row.phase_timings[phase]) || dashboard.events.some(event => event.normalized_phase === phase));
      populateSelect("phaseFilter", [["all", "All phases"], ...phases.map(p => [p, labelPhase(p)])], state.phase);
      populateSelect("groupFilter", [["all", "All HTTP groups"], ...dashboard.http_groups.map(g => [g, labelGroup(g)])], state.group);
      populateSelect("metricFilter", metricOptions, state.metric);
      document.getElementById("searchFilter").value = state.query;
    }

    function bindControls() {
      for (const [id, key] of [
        ["sizeFilter", "size"],
        ["phaseFilter", "phase"],
        ["groupFilter", "group"],
        ["metricFilter", "metric"]
      ]) {
        document.getElementById(id).addEventListener("change", event => {
          state[key] = event.target.value;
          render();
        });
      }
      const picker = document.getElementById("targetPicker");
      document.getElementById("targetPickerButton").addEventListener("click", () => {
        picker.classList.toggle("open");
      });
      document.getElementById("targetPickerMenu").addEventListener("change", event => {
        if (event.target.value === "__all__") {
          state.targets = event.target.checked ? [...dashboard.targets] : [];
        } else if (event.target.checked) {
          state.targets = [...new Set([...state.targets, event.target.value])];
        } else {
          state.targets = state.targets.filter(target => target !== event.target.value);
        }
        updateTargetPicker();
        render();
      });
      document.addEventListener("click", event => {
        if (!picker.contains(event.target)) picker.classList.remove("open");
      });
      document.addEventListener("keydown", event => {
        if (event.key === "Escape") picker.classList.remove("open");
      });
      document.getElementById("searchFilter").addEventListener("input", event => {
        state.query = event.target.value;
        render();
      });
    }

    function renderStats(rows, events) {
      const passed = rows.filter(row => row.passed).length;
      const targetGroups = groupBy(rows, row => row.target);
      let slowest = "";
      let slowestValue = -Infinity;
      for (const [target, targetRows] of targetGroups) {
        const value = median(targetRows.map(row => Number(row.workload_wall_s)));
        if (value > slowestValue) {
          slowest = target;
          slowestValue = value;
        }
      }
      const totalRequests = sum(events.map(event => Number(event.duration_ms) >= 0 ? 1 : 0));
      const totalHttpMs = sum(events.map(event => Number(event.duration_ms)));
      const cards = [
        ["Runs", fmtNumber(rows.length), `${passed}/${rows.length} passed`],
        ["Median workload", fmtSeconds(median(rows.map(row => Number(row.workload_wall_s)))), "create through cleanup"],
        ["Median HTTP", fmtMs(median(rows.map(row => Number(row.http_duration_ms)))), "summed request durations"],
        ["HTTP requests", fmtNumber(totalRequests), fmtMs(totalHttpMs)],
        ["Slowest catalog", slowest ? labelTarget(slowest) : "", slowest ? fmtSeconds(slowestValue) : ""]
      ];
      document.getElementById("stats").innerHTML = cards.map(([label, value, note]) => `
        <div class="stat">
          <div class="label">${escapeHtml(label)}</div>
          <div class="value">${escapeHtml(value)}</div>
          <div class="note">${escapeHtml(note)}</div>
        </div>
      `).join("");
    }

    function barSvg(items, options) {
      const width = 920;
      const rowHeight = options.rowHeight || 34;
      const labelWidth = options.labelWidth || 205;
      const valueWidth = 94;
      const chartWidth = width - labelWidth - valueWidth - 22;
      const height = Math.max(70, 30 + items.length * rowHeight);
      const maxValue = Math.max(...items.map(item => item.value), 0);
      const scale = value => maxValue > 0 ? (value / maxValue) * chartWidth : 0;
      const rows = items.map((item, index) => {
        const y = 24 + index * rowHeight;
        const barWidth = Math.max(item.value > 0 ? 2 : 0, scale(item.value));
        return `
          <g>
            <text x="0" y="${y + 15}" class="bar-label">${escapeHtml(item.label)}</text>
            <rect x="${labelWidth}" y="${y}" width="${chartWidth}" height="19" rx="3" fill="#edf2f6"></rect>
            <rect x="${labelWidth}" y="${y}" width="${barWidth}" height="19" rx="3" fill="${item.color}"></rect>
            <text x="${labelWidth + chartWidth + 12}" y="${y + 15}" class="caption">${escapeHtml(item.valueLabel)}</text>
          </g>
        `;
      }).join("");
      return `<svg viewBox="0 0 ${width} ${height}" role="img">${rows}</svg>`;
    }

    function renderComparison(rows) {
      const groups = [...groupBy(rows, row => `${row.target}|${row.size}`).entries()];
      const items = groups.map(([key, groupRows], index) => {
        const [target, size] = key.split("|");
        const value = median(groupRows.map(row => Number(row[state.metric])));
        return {
          label: `${labelTarget(target)} / ${size}`,
          value,
          valueLabel: fmtMetric(value, state.metric),
          color: colors[index % colors.length],
          target
        };
      }).sort((a, b) => b.value - a.value);
      document.getElementById("comparisonChart").innerHTML = items.length
        ? barSvg(items, { labelWidth: 245 })
        : "<div class=\"caption\">No rows match current filters.</div>";
      renderLegend("comparisonLegend", [...new Set(items.map(item => item.target))].map((target, index) => ({
        label: labelTarget(target),
        color: colors[index % colors.length]
      })));
    }

    function renderLegend(id, items) {
      document.getElementById(id).innerHTML = items.map(item => `
        <span class="legend-item"><span class="swatch" style="background:${item.color}"></span>${escapeHtml(item.label)}</span>
      `).join("");
    }

    function renderPhaseChart(rows) {
      const phases = dashboard.workload_phases;
      const groups = [...groupBy(rows, row => `${row.target}|${row.size}`).entries()]
        .map(([key, groupRows]) => {
          const [target, size] = key.split("|");
          const values = {};
          for (const phase of phases) {
            values[phase] = median(groupRows.map(row => Number(row.phase_timings[phase] || 0)));
          }
          return { target, size, label: `${labelTarget(target)} / ${size}`, values, total: sum(Object.values(values)) };
        })
        .sort((a, b) => b.total - a.total);

      const width = 920;
      const labelWidth = 245;
      const valueWidth = 88;
      const chartWidth = width - labelWidth - valueWidth - 22;
      const rowHeight = 36;
      const height = Math.max(78, 30 + groups.length * rowHeight);
      const maxTotal = Math.max(...groups.map(group => group.total), 0);
      const rowsSvg = groups.map((group, index) => {
        let x = labelWidth;
        const y = 24 + index * rowHeight;
        const segments = phases.map(phase => {
          const value = group.values[phase];
          const widthValue = maxTotal > 0 ? (value / maxTotal) * chartWidth : 0;
          const rect = `<rect x="${x}" y="${y}" width="${Math.max(value > 0 ? 1 : 0, widthValue)}" height="20" fill="${phaseColors[phase] || "#63758a"}"></rect>`;
          x += widthValue;
          return rect;
        }).join("");
        return `
          <g>
            <text x="0" y="${y + 15}" class="bar-label">${escapeHtml(group.label)}</text>
            <rect x="${labelWidth}" y="${y}" width="${chartWidth}" height="20" rx="3" fill="#edf2f6"></rect>
            ${segments}
            <text x="${labelWidth + chartWidth + 12}" y="${y + 15}" class="caption">${escapeHtml(fmtSeconds(group.total))}</text>
          </g>
        `;
      }).join("");
      document.getElementById("phaseChart").innerHTML = groups.length
        ? `<svg viewBox="0 0 ${width} ${height}" role="img">${rowsSvg}</svg>`
        : "<div class=\"caption\">No rows match current filters.</div>";
      renderLegend("phaseLegend", phases.map(phase => ({ label: labelPhase(phase), color: phaseColors[phase] || "#63758a" })));
    }

    function renderHttpGroupChart(events) {
      const grouped = [...groupBy(events, event => event.url_group).entries()]
        .map(([group, groupEvents], index) => ({
          label: labelGroup(group),
          value: sum(groupEvents.map(event => Number(event.duration_ms))),
          valueLabel: `${fmtMs(sum(groupEvents.map(event => Number(event.duration_ms))))} / ${fmtNumber(groupEvents.length)} req`,
          color: colors[index % colors.length],
          group
        }))
        .sort((a, b) => b.value - a.value);
      document.getElementById("httpGroupChart").innerHTML = grouped.length
        ? barSvg(grouped, { labelWidth: 245 })
        : "<div class=\"caption\">No HTTP requests match current filters.</div>";
      renderLegend("httpLegend", grouped.map(item => ({ label: item.label, color: item.color })));
    }

    function phaseListForAttribution() {
      if (state.phase !== "all") return [state.phase];
      return dashboard.workload_phases;
    }

    function phaseAttribution(row, phase) {
      const wallMs = Number(row.phase_timings[phase] || 0) * 1000;
      const groups = ((row.http_phase_groups || {})[phase]) || {};
      let catalogMs = 0;
      let objectMs = 0;
      let otherHttpMs = 0;
      for (const [group, values] of Object.entries(groups)) {
        const duration = Number(values.duration_ms || 0);
        if (group.startsWith("rest_")) catalogMs += duration;
        else if (group.startsWith("object_")) objectMs += duration;
        else otherHttpMs += duration;
      }
      const httpMs = catalogMs + objectMs + otherHttpMs;
      return {
        run_key: row.run_key,
        target: row.target,
        target_label: row.target_label,
        size: row.size,
        phase,
        wall_ms: wallMs,
        catalog_ms: catalogMs,
        object_ms: objectMs,
        other_http_ms: otherHttpMs,
        http_ms: httpMs,
        local_ms: Math.max(0, wallMs - httpMs),
        catalog_pct: wallMs > 0 ? (catalogMs / wallMs) * 100 : NaN
      };
    }

    function attributionRows(rows) {
      const phases = phaseListForAttribution();
      const entries = [];
      for (const row of rows) {
        for (const phase of phases) {
          if (row.phase_timings[phase] === undefined) continue;
          entries.push(phaseAttribution(row, phase));
        }
      }
      return entries;
    }

    function medianAttribution(entries) {
      return {
        target: entries[0].target,
        target_label: entries[0].target_label,
        size: entries[0].size,
        phase: entries[0].phase,
        wall_ms: median(entries.map(entry => Number(entry.wall_ms))),
        catalog_ms: median(entries.map(entry => Number(entry.catalog_ms))),
        object_ms: median(entries.map(entry => Number(entry.object_ms))),
        other_http_ms: median(entries.map(entry => Number(entry.other_http_ms))),
        http_ms: median(entries.map(entry => Number(entry.http_ms))),
        local_ms: median(entries.map(entry => Number(entry.local_ms)))
      };
    }

    function renderAttributionChart(rows) {
      const perRun = [...groupBy(attributionRows(rows), entry => `${entry.target}|${entry.size}|${entry.run_key || ""}`).values()]
        .map(entries => ({
          target: entries[0].target,
          target_label: entries[0].target_label,
          size: entries[0].size,
          wall_ms: sum(entries.map(entry => entry.wall_ms)),
          catalog_ms: sum(entries.map(entry => entry.catalog_ms)),
          object_ms: sum(entries.map(entry => entry.object_ms)),
          other_http_ms: sum(entries.map(entry => entry.other_http_ms)),
          local_ms: sum(entries.map(entry => entry.local_ms))
        }));
      const grouped = [...groupBy(perRun, entry => `${entry.target}|${entry.size}`).entries()]
        .map(([, entries]) => ({
          target: entries[0].target,
          target_label: entries[0].target_label,
          size: entries[0].size,
          wall_ms: median(entries.map(entry => entry.wall_ms)),
          catalog_ms: median(entries.map(entry => entry.catalog_ms)),
          object_ms: median(entries.map(entry => entry.object_ms)),
          other_http_ms: median(entries.map(entry => entry.other_http_ms)),
          local_ms: median(entries.map(entry => entry.local_ms))
        }))
        .sort((a, b) => b.wall_ms - a.wall_ms);

      const width = 920;
      const labelWidth = 245;
      const valueWidth = 92;
      const chartWidth = width - labelWidth - valueWidth - 22;
      const rowHeight = 36;
      const height = Math.max(78, 30 + grouped.length * rowHeight);
      const maxValue = Math.max(...grouped.map(group => group.wall_ms), 0);
      const rowsSvg = grouped.map((group, index) => {
        let x = labelWidth;
        const y = 24 + index * rowHeight;
        const segments = attributionParts.map(([key, , color]) => {
          const value = Number(group[key] || 0);
          const widthValue = maxValue > 0 ? (value / maxValue) * chartWidth : 0;
          const rect = `<rect x="${x}" y="${y}" width="${Math.max(value > 0 ? 1 : 0, widthValue)}" height="20" fill="${color}"></rect>`;
          x += widthValue;
          return rect;
        }).join("");
        return `
          <g>
            <text x="0" y="${y + 15}" class="bar-label">${escapeHtml(group.target_label)} / ${escapeHtml(group.size)}</text>
            <rect x="${labelWidth}" y="${y}" width="${chartWidth}" height="20" rx="3" fill="#edf2f6"></rect>
            ${segments}
            <text x="${labelWidth + chartWidth + 12}" y="${y + 15}" class="caption">${escapeHtml(fmtMs(group.wall_ms))}</text>
          </g>
        `;
      }).join("");

      document.getElementById("attributionChart").innerHTML = grouped.length
        ? `<svg viewBox="0 0 ${width} ${height}" role="img">${rowsSvg}</svg>`
        : "<div class=\"caption\">No attribution rows match current filters.</div>";
      renderLegend("attributionLegend", attributionParts.map(([, label, color]) => ({ label, color })));
    }

    function renderAttributionTable(rows) {
      const grouped = [...groupBy(attributionRows(rows), entry => `${entry.target}|${entry.size}|${entry.phase}`).values()]
        .map(entries => {
          const row = medianAttribution(entries);
          row.catalog_pct = row.wall_ms > 0 ? (row.catalog_ms / row.wall_ms) * 100 : NaN;
          return row;
        })
        .sort((a, b) => b.catalog_ms - a.catalog_ms);
      const body = grouped.map(row => `
        <tr>
          <td>${escapeHtml(row.target_label)}</td>
          <td>${escapeHtml(row.size)}</td>
          <td>${escapeHtml(labelPhase(row.phase))}</td>
          <td class="num">${escapeHtml(fmtMs(row.wall_ms))}</td>
          <td class="num">${escapeHtml(fmtMs(row.catalog_ms))}</td>
          <td class="num">${escapeHtml(fmtMs(row.object_ms))}</td>
          <td class="num">${escapeHtml(fmtMs(row.other_http_ms))}</td>
          <td class="num">${escapeHtml(fmtMs(row.local_ms))}</td>
          <td class="num">${escapeHtml(fmtPercent(row.catalog_pct))}</td>
        </tr>
      `).join("");
      document.getElementById("attributionTable").innerHTML = `
        <thead><tr>
          <th>Target</th><th>Size</th><th>Phase</th><th class="num">Wall</th>
          <th class="num">Catalog REST</th><th class="num">Object store</th>
          <th class="num">Other HTTP</th><th class="num">DuckDB/local</th>
          <th class="num">Catalog %</th>
        </tr></thead>
        <tbody>${body || "<tr><td colspan=\"9\">No attribution rows match current filters.</td></tr>"}</tbody>
      `;
    }

    function heatColor(value, maxValue) {
      if (!value || !maxValue) return "#f7f9fb";
      const ratio = Math.log10(value + 1) / Math.log10(maxValue + 1);
      const lightness = 96 - ratio * 42;
      return `hsl(189 58% ${lightness}%)`;
    }

    function renderHeatmap(events) {
      const phases = dashboard.workload_phases;
      const targets = dashboard.targets.filter(target => targetIsSelected(target));
      const totals = new Map();
      for (const event of events) {
        const key = `${event.target}|${event.normalized_phase}`;
        totals.set(key, (totals.get(key) || 0) + Number(event.duration_ms || 0));
      }
      const maxValue = Math.max(...totals.values(), 0);
      const header = `
        <div class="heatmap-row">
          <div class="heatmap-cell heatmap-head">Target</div>
          ${phases.map(phase => `<div class="heatmap-cell heatmap-head">${escapeHtml(labelPhase(phase))}</div>`).join("")}
        </div>
      `;
      const rows = targets.map(target => `
        <div class="heatmap-row">
          <div class="heatmap-cell"><strong>${escapeHtml(labelTarget(target))}</strong></div>
          ${phases.map(phase => {
            const value = totals.get(`${target}|${phase}`) || 0;
            return `
              <div class="heatmap-cell" style="background:${heatColor(value, maxValue)}">
                <div class="heatmap-value">${escapeHtml(fmtMs(value))}</div>
                <div class="heatmap-note">${escapeHtml(labelGroup(state.group === "all" ? "" : state.group))}</div>
              </div>
            `;
          }).join("")}
        </div>
      `).join("");
      const element = document.getElementById("heatmap");
      element.style.setProperty("--phase-count", phases.length);
      element.innerHTML = `<div class="heatmap">${header}${rows}</div>`;
    }

    function renderRequestTable(events) {
      const top = [...events].sort((a, b) => Number(b.duration_ms) - Number(a.duration_ms)).slice(0, 250);
      const rows = top.map(event => `
        <tr>
          <td>${escapeHtml(event.target_label)}</td>
          <td>${escapeHtml(event.size)} r${escapeHtml(event.repetition)}</td>
          <td>${escapeHtml(labelPhase(event.normalized_phase))}</td>
          <td>${escapeHtml(labelGroup(event.url_group))}</td>
          <td>${escapeHtml(event.method)}</td>
          <td>${escapeHtml(event.status)}</td>
          <td class="num">${escapeHtml(fmtMs(Number(event.duration_ms)))}</td>
          <td class="mono">${escapeHtml(event.host)}${escapeHtml(event.path)}</td>
          <td><a href="${escapeHtml(event.artifact_href)}">JSONL:${escapeHtml(event.line)}</a></td>
        </tr>
      `).join("");
      document.getElementById("requestTable").innerHTML = `
        <thead><tr>
          <th>Target</th><th>Run</th><th>Phase</th><th>Group</th><th>Method</th>
          <th>Status</th><th class="num">Duration</th><th>Path</th><th>Source</th>
        </tr></thead>
        <tbody>${rows || "<tr><td colspan=\"9\">No requests match current filters.</td></tr>"}</tbody>
      `;
    }

    function renderStatusTable(events) {
      const grouped = [...groupBy(events, event => `${event.target}|${event.method}|${event.status}|${event.url_group}`).entries()]
        .map(([key, groupEvents]) => {
          const [target, method, status, urlGroup] = key.split("|");
          return {
            target,
            method,
            status,
            urlGroup,
            count: groupEvents.length,
            duration: sum(groupEvents.map(event => Number(event.duration_ms)))
          };
        })
        .sort((a, b) => b.duration - a.duration);
      const rows = grouped.map(item => `
        <tr>
          <td>${escapeHtml(labelTarget(item.target))}</td>
          <td>${escapeHtml(item.method)}</td>
          <td>${escapeHtml(item.status)}</td>
          <td>${escapeHtml(labelGroup(item.urlGroup))}</td>
          <td class="num">${escapeHtml(fmtNumber(item.count))}</td>
          <td class="num">${escapeHtml(fmtMs(item.duration))}</td>
        </tr>
      `).join("");
      document.getElementById("statusTable").innerHTML = `
        <thead><tr><th>Target</th><th>Method</th><th>Status</th><th>Group</th><th class="num">Requests</th><th class="num">Duration</th></tr></thead>
        <tbody>${rows || "<tr><td colspan=\"6\">No status rows match current filters.</td></tr>"}</tbody>
      `;
    }

    function renderRunTable(rows) {
      const sorted = [...rows].sort((a, b) => Number(b.workload_wall_s) - Number(a.workload_wall_s));
      const body = sorted.map(row => {
        const links = row.artifact_links || {};
        const linkHtml = Object.entries(links).map(([name, href]) => `<a href="${escapeHtml(href)}">${escapeHtml(name)}</a>`).join("");
        return `
          <tr>
            <td>${escapeHtml(row.target_label)}</td>
            <td>${escapeHtml(row.variant)}</td>
            <td>${escapeHtml(row.size)}</td>
            <td class="num">${escapeHtml(fmtNumber(Number(row.rows)))}</td>
            <td class="num">${escapeHtml(row.repetition)}</td>
            <td class="${row.passed ? "status-ok" : "status-bad"}">${row.passed ? "passed" : "failed"}</td>
            <td class="num">${escapeHtml(fmtSeconds(Number(row.workload_wall_s)))}</td>
            <td class="num">${escapeHtml(fmtSeconds(Number(row.total_wall_s)))}</td>
            <td class="num">${escapeHtml(fmtMs(Number(row.http_duration_ms)))}</td>
            <td class="num">${escapeHtml(fmtNumber(Number(row.http_request_count)))}</td>
            <td class="links">${linkHtml}</td>
          </tr>
        `;
      }).join("");
      document.getElementById("runTable").innerHTML = `
        <thead><tr>
          <th>Target</th><th>Variant</th><th>Size</th><th class="num">Rows</th><th class="num">Rep</th>
          <th>Result</th><th class="num">Workload</th><th class="num">Total</th>
          <th class="num">HTTP</th><th class="num">Requests</th><th>Artifacts</th>
        </tr></thead>
        <tbody>${body || "<tr><td colspan=\"11\">No runs match current filters.</td></tr>"}</tbody>
      `;
    }

    function renderArtifactTable() {
      const query = state.query.trim().toLowerCase();
      const artifacts = dashboard.artifacts.filter(artifact => {
        if (artifact.target && !targetIsSelected(artifact.target)) return false;
        if (query && !artifact.path.toLowerCase().includes(query)) return false;
        return true;
      });
      const rows = artifacts.map(artifact => `
        <tr>
          <td class="mono"><a href="${escapeHtml(artifact.href)}">${escapeHtml(artifact.path)}</a></td>
          <td>${escapeHtml(artifact.target)}</td>
          <td>${escapeHtml(artifact.kind)}</td>
          <td class="num">${escapeHtml(artifact.size_label)}</td>
        </tr>
      `).join("");
      document.getElementById("artifactTable").innerHTML = `
        <thead><tr><th>Path</th><th>Target</th><th>Kind</th><th class="num">Size</th></tr></thead>
        <tbody>${rows || "<tr><td colspan=\"4\">No artifacts match current filters.</td></tr>"}</tbody>
      `;
    }

    function render() {
      const rows = filteredRows();
      const events = filteredEvents();
      renderStats(rows, events);
      renderComparison(rows);
      renderPhaseChart(rows);
      renderHttpGroupChart(events);
      renderHeatmap(events);
      renderAttributionChart(rows);
      renderAttributionTable(rows);
      renderRequestTable(events);
      renderStatusTable(events);
      renderRunTable(rows);
      renderArtifactTable();
    }

    populateControls();
    bindControls();
    render();
  </script>
</body>
</html>
"""


def render_html(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    return (
        HTML_TEMPLATE.replace("__RUN_ID__", str(data["run_id"]))
        .replace("__RUN_ROOT__", str(data["run_root"]))
        .replace("__GENERATED_AT__", str(data["generated_at"]))
        .replace("__DATA__", encoded)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-root",
        type=Path,
        default=None,
        help="benchmark run root, defaults to newest .tmp/catalog_benchmarks run",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path, defaults to reports/<run_id>-dashboard.html",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_root = (args.run_root or default_run_root()).resolve()
    output_path = (args.output or (REPORTS_DIR / f"{run_root.name}-dashboard.html")).resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_dashboard_data(run_root, output_path)
    output_path.write_text(render_html(data))
    print(f"wrote {output_path.relative_to(ROOT)}")
    print(f"embedded {len(data['rows'])} runs and {len(data['events'])} HTTP events")


if __name__ == "__main__":
    main()
