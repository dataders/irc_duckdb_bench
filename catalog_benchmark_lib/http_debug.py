from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
HTTP_DEBUG_RE = re.compile(
    r"\{'request': \{'type': ([A-Z]+), .*?'url': '([^']+)'.*?'duration_ms': ([0-9]+)"
    r".*?'response': \{'status': ([A-Za-z0-9_]+)",
)


def classify_url(url: str) -> str:
    clean = url.split("?", 1)[0]
    if "/v1/config" in clean or clean.endswith("/config"):
        return "rest_config"
    if "/transactions/commit" in clean or "/tables/" in clean:
        return "rest_table_commit_or_load"
    if clean.endswith("/tables"):
        return "rest_create_table"
    if "/namespaces" in clean:
        return "rest_namespace"
    if "/data/" in clean or clean.endswith(".parquet"):
        return "object_data"
    if "/metadata/" in clean or clean.endswith((".avro", ".metadata.json")):
        return "object_metadata"
    return "other"


def summarize_http_log(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {"http_request_count": 0, "http_duration_ms": 0, "http_groups": {}}
    text = path.read_text(errors="replace")
    groups: dict[str, dict[str, float | int]] = {}
    total = 0
    count = 0
    for match in re.finditer(r"'url': '([^']+)'.*?'duration_ms': ([0-9]+)", text):
        url = match.group(1)
        duration = int(match.group(2))
        group = classify_url(url)
        bucket = groups.setdefault(group, {"count": 0, "duration_ms": 0})
        bucket["count"] = int(bucket["count"]) + 1
        bucket["duration_ms"] = float(bucket["duration_ms"]) + duration
        total += duration
        count += 1
    return {"http_request_count": count, "http_duration_ms": total, "http_groups": groups}


def parse_http_debug_output(output: str) -> list[dict[str, Any]]:
    current_phase = "startup"
    events = []
    for raw_line in output.splitlines():
        line = ANSI_ESCAPE_RE.sub("", raw_line)
        if line.startswith(">>> PHASE: "):
            current_phase = line.removeprefix(">>> PHASE: ").strip()
            continue
        if "{'request':" not in line:
            continue
        match = HTTP_DEBUG_RE.search(line)
        if not match:
            continue
        method, url, duration_ms, status = match.groups()
        parsed_url = urllib.parse.urlsplit(url)
        events.append(
            {
                "phase": current_phase,
                "method": method,
                "status": status,
                "duration_ms": int(duration_ms),
                "url_group": classify_url(url),
                "host": parsed_url.netloc,
                "path": parsed_url.path,
            }
        )
    return events


def summarize_http_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, int]] = {}
    phase_groups: dict[str, dict[str, dict[str, int]]] = {}
    total = 0
    for event in events:
        duration = int(event["duration_ms"])
        group = str(event["url_group"])
        phase = str(event["phase"])
        bucket = groups.setdefault(group, {"count": 0, "duration_ms": 0})
        bucket["count"] += 1
        bucket["duration_ms"] += duration
        phase_bucket = phase_groups.setdefault(phase, {}).setdefault(
            group, {"count": 0, "duration_ms": 0}
        )
        phase_bucket["count"] += 1
        phase_bucket["duration_ms"] += duration
        total += duration
    return {
        "http_request_count": len(events),
        "http_duration_ms": total,
        "http_groups": groups,
        "http_phase_groups": phase_groups,
    }


def write_http_debug_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n")
