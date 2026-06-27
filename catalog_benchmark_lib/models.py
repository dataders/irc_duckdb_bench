from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SIZES = {
    "tiny": 4,
    "small": 10_000,
    "medium": 1_000_000,
    "large": 10_000_000,
}
TPCH_LINEITEM_ROWS_PER_SCALE_FACTOR = 6_001_215
DEFAULT_SCALE_FACTORS = "0.01,0.1"


@dataclass(frozen=True)
class BenchmarkSize:
    label: str
    rows: int
    scale_factor: float | None = None


@dataclass(frozen=True)
class AttachVariant:
    name: str
    options: dict[str, str]


@dataclass(frozen=True)
class CatalogTarget:
    name: str
    description: str
    default_variant: str
    attach_as: str
    warehouse: str
    endpoint: str
    endpoint_type: str | None
    default_schema: str
    authorization_type: str | None
    access_delegation_mode: str | None
    default_region: str | None
    create_schema: bool
    required_env: list[str]
    table_location_root: str | None
    aws_secret: dict[str, str]
    token_secret: dict[str, str]
    oauth_secret: dict[str, str]
    s3_secret: dict[str, str]


ATTACH_VARIANTS = {
    "default": AttachVariant("default", {}),
    "no_stage_create": AttachVariant("no_stage_create", {"STAGE_CREATE_TABLES": "false"}),
    "no_stage_no_purge": AttachVariant(
        "no_stage_no_purge",
        {"STAGE_CREATE_TABLES": "false", "PURGE_REQUESTED": "false"},
    ),
    "no_multi_commit": AttachVariant("no_multi_commit", {"DISABLE_MULTI_TABLE_COMMIT": "true"}),
    "skip_create_metadata_updates": AttachVariant(
        "skip_create_metadata_updates",
        {"STAGE_CREATE_TABLES": "false", "SKIP_CREATE_TABLE_METADATA_UPDATES": "true"},
    ),
    "stage_multi_metadata": AttachVariant(
        "stage_multi_metadata",
        {
            "STAGE_CREATE_TABLES": "false",
            "DISABLE_MULTI_TABLE_COMMIT": "true",
            "SKIP_CREATE_TABLE_METADATA_UPDATES": "true",
        },
    ),
    "no_cleanup_on_rollback": AttachVariant(
        "no_cleanup_on_rollback", {"REMOVE_FILES_ON_DELETE": "false"}
    ),
    "legacy_without_stage_create": AttachVariant(
        "legacy_without_stage_create",
        {
            "DISABLE_MULTI_TABLE_COMMIT": "true",
            "SKIP_CREATE_TABLE_METADATA_UPDATES": "true",
            "REMOVE_FILES_ON_DELETE": "false",
        },
    ),
    "legacy_full_compat": AttachVariant(
        "legacy_full_compat",
        {
            "STAGE_CREATE_TABLES": "false",
            "DISABLE_MULTI_TABLE_COMMIT": "true",
            "SKIP_CREATE_TABLE_METADATA_UPDATES": "true",
            "REMOVE_FILES_ON_DELETE": "false",
            "READ_ONLY": "false",
        },
    ),
}
