from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from catalog_benchmark_lib.models import (
    DEFAULT_SCALE_FACTORS,
    DEFAULT_SIZES,
    TPCH_LINEITEM_ROWS_PER_SCALE_FACTOR,
    BenchmarkSize,
    CatalogTarget,
)
from catalog_benchmark_lib.paths import ROOT, TARGET_CONFIG


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def merged_env() -> dict[str, str]:
    env = load_dotenv(ROOT / ".env")
    env.update(os.environ)
    return env


def resolve_template(value: Any, env: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_template(nested, env) for key, nested in value.items()}
    if isinstance(value, list):
        return [resolve_template(nested, env) for nested in value]
    if not isinstance(value, str):
        return value

    pattern = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        default = match.group(2)
        if key in env and env[key] != "":
            return env[key]
        if default is not None:
            return resolve_template(default, env)
        return ""

    return pattern.sub(replace, value)


def load_targets(env: dict[str, str] | None = None) -> dict[str, CatalogTarget]:
    env = env or merged_env()
    raw = tomllib.loads(TARGET_CONFIG.read_text())["targets"]
    targets = {}
    for name, values in raw.items():
        resolved = {key: resolve_template(value, env) for key, value in values.items()}
        targets[name] = CatalogTarget(
            name=name,
            description=str(resolved.get("description", "")),
            default_variant=str(resolved.get("default_variant", "default")),
            attach_as=str(resolved["attach_as"]),
            warehouse=str(resolved["warehouse"]),
            endpoint=str(resolved.get("endpoint", "")),
            endpoint_type=resolved.get("endpoint_type"),
            default_schema=str(resolved["default_schema"]),
            authorization_type=resolved.get("authorization_type"),
            access_delegation_mode=resolved.get("access_delegation_mode"),
            default_region=resolved.get("default_region"),
            create_schema=bool(resolved.get("create_schema", False)),
            required_env=list(values.get("required_env", [])),
            table_location_root=resolved.get("table_location_root"),
            aws_secret=dict(resolved.get("aws_secret", {})),
            token_secret=dict(resolved.get("token_secret", {})),
            oauth_secret=dict(resolved.get("oauth_secret", {})),
            s3_secret=dict(resolved.get("s3_secret", {})),
        )
        if targets[name].oauth_secret and not targets[name].oauth_secret.get("oauth2_server_uri"):
            secret = dict(targets[name].oauth_secret)
            secret["oauth2_server_uri"] = targets[name].endpoint.rstrip("/") + "/v1/oauth/tokens"
            targets[name] = CatalogTarget(
                name=targets[name].name,
                description=targets[name].description,
                default_variant=targets[name].default_variant,
                attach_as=targets[name].attach_as,
                warehouse=targets[name].warehouse,
                endpoint=targets[name].endpoint,
                endpoint_type=targets[name].endpoint_type,
                default_schema=targets[name].default_schema,
                authorization_type=targets[name].authorization_type,
                access_delegation_mode=targets[name].access_delegation_mode,
                default_region=targets[name].default_region,
                create_schema=targets[name].create_schema,
                required_env=targets[name].required_env,
                table_location_root=targets[name].table_location_root,
                aws_secret=targets[name].aws_secret,
                token_secret=targets[name].token_secret,
                oauth_secret=secret,
                s3_secret=targets[name].s3_secret,
            )
    return targets


def missing_env(target: CatalogTarget, env: dict[str, str]) -> list[str]:
    return [name for name in target.required_env if not env.get(name)]


def parse_size_matrix(sizes: str | None, rows: str | None) -> list[BenchmarkSize]:
    if rows:
        parsed = []
        for raw_row_count in rows.split(","):
            raw_row_count = raw_row_count.strip()
            if not raw_row_count:
                continue
            row_count = int(raw_row_count.replace("_", ""))
            if row_count <= 0:
                raise ValueError(f"row count must be positive: {raw_row_count}")
            parsed.append(BenchmarkSize(f"rows_{row_count}", row_count))
        if parsed:
            return parsed

    selected = sizes.split(",") if sizes else ["tiny", "small"]
    parsed = []
    for raw_name in selected:
        name = raw_name.strip()
        if not name:
            continue
        if name not in DEFAULT_SIZES:
            valid = ", ".join(DEFAULT_SIZES)
            raise ValueError(f"unknown size {name!r}; valid sizes: {valid}")
        parsed.append(BenchmarkSize(name, DEFAULT_SIZES[name]))
    return parsed


def scale_factor_label(scale_factor: float) -> str:
    return f"sf_{scale_factor:g}".replace(".", "_").replace("-", "m")


def parse_scale_factor_matrix(scale_factors: str | None) -> list[BenchmarkSize]:
    selected = scale_factors or DEFAULT_SCALE_FACTORS
    parsed = []
    for raw_scale_factor in selected.split(","):
        raw_scale_factor = raw_scale_factor.strip()
        if not raw_scale_factor:
            continue
        scale_factor = float(raw_scale_factor)
        if scale_factor <= 0:
            raise ValueError(f"scale factor must be positive: {raw_scale_factor}")
        rows = round(TPCH_LINEITEM_ROWS_PER_SCALE_FACTOR * scale_factor)
        parsed.append(BenchmarkSize(scale_factor_label(scale_factor), rows, scale_factor))
    return parsed


def parse_benchmark_matrix(
    workload: str, sizes: str | None, rows: str | None, scale_factors: str | None
) -> list[BenchmarkSize]:
    if workload == "tpch-read":
        if rows:
            raise ValueError("--rows cannot be combined with --workload tpch-read")
        return parse_scale_factor_matrix(scale_factors)
    if scale_factors:
        raise ValueError("--scale-factors requires --workload tpch-read")
    return parse_size_matrix(sizes, rows)
