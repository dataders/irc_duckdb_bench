from __future__ import annotations

import re
from pathlib import Path

from catalog_benchmark_lib.models import AttachVariant, BenchmarkSize, CatalogTarget
from catalog_benchmark_lib.paths import RUN_TEMPLATE


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def option_sql(name: str, value: str | bool) -> str:
    if isinstance(value, bool):
        return f"  {name} {'true' if value else 'false'}"
    if name in {"TYPE", "SECRET", "PROVIDER"}:
        return f"  {name} {value}"
    if value in {"true", "false"}:
        return f"  {name} {value}"
    return f"  {name} {sql_literal(value)}"


def render_secret_sql(target: CatalogTarget, env: dict[str, str]) -> str:
    statements = []
    if target.aws_secret:
        secret = target.aws_secret
        options: list[tuple[str, str]] = [("TYPE", "S3"), ("PROVIDER", "credential_chain")]
        if secret.get("region"):
            options.append(("REGION", secret["region"]))
        rendered_options = ", ".join(option_sql(name, value) for name, value in options)
        statements.append(f"CREATE OR REPLACE SECRET {secret['name']} ({rendered_options});")
    if target.s3_secret:
        secret = target.s3_secret
        statements.append(
            "CREATE OR REPLACE SECRET {name} (TYPE S3, KEY_ID {key_id}, SECRET {secret}, "
            "ENDPOINT {endpoint}, URL_STYLE {url_style}, USE_SSL {use_ssl});".format(
                name=secret["name"],
                key_id=sql_literal(secret["key_id"]),
                secret=sql_literal(secret["secret"]),
                endpoint=sql_literal(secret["endpoint"]),
                url_style=sql_literal(secret.get("url_style", "path")),
                use_ssl="true" if secret.get("use_ssl") else "false",
            )
        )
    if target.token_secret:
        secret = target.token_secret
        statements.append(
            "CREATE OR REPLACE SECRET {name} (TYPE ICEBERG, TOKEN {token});".format(
                name=secret["name"],
                token=sql_literal(secret["token"]),
            )
        )
    if target.oauth_secret:
        secret = target.oauth_secret
        statements.append(
            "CREATE OR REPLACE SECRET {name} "
            "(TYPE ICEBERG, CLIENT_ID {client_id}, CLIENT_SECRET {client_secret}, "
            "OAUTH2_SERVER_URI {oauth2_server_uri}, OAUTH2_SCOPE {oauth2_scope}, "
            "OAUTH2_GRANT_TYPE {oauth2_grant_type});".format(
                name=secret["name"],
                client_id=sql_literal(secret["client_id"]),
                client_secret=sql_literal(secret["client_secret"]),
                oauth2_server_uri=sql_literal(secret["oauth2_server_uri"]),
                oauth2_scope=sql_literal(secret.get("oauth2_scope", "PRINCIPAL_ROLE:ALL")),
                oauth2_grant_type=sql_literal(
                    secret.get("oauth2_grant_type", "client_credentials")
                ),
            )
        )
    if not statements:
        return "SELECT 'no secrets required' AS benchmark_secret_status;"
    return "\n".join(statements)


def secret_name(target: CatalogTarget) -> str | None:
    if target.token_secret:
        return target.token_secret["name"]
    if target.oauth_secret:
        return target.oauth_secret["name"]
    return None


def render_attach_sql(target: CatalogTarget, env: dict[str, str], variant: AttachVariant) -> str:
    options: list[tuple[str, str | bool]] = [
        ("TYPE", "ICEBERG"),
    ]
    if target.endpoint_type:
        options.append(("ENDPOINT_TYPE", target.endpoint_type))
    else:
        options.append(("ENDPOINT", target.endpoint))
    target_secret = secret_name(target)
    if target_secret:
        options.append(("SECRET", target_secret))
    if target.authorization_type:
        options.append(("AUTHORIZATION_TYPE", target.authorization_type))
    if target.access_delegation_mode:
        options.append(("ACCESS_DELEGATION_MODE", target.access_delegation_mode))
    if target.default_region and not target.endpoint_type:
        options.append(("DEFAULT_REGION", target.default_region))
    if target.default_schema:
        options.append(("DEFAULT_SCHEMA", target.default_schema))
    options.extend(variant.options.items())

    rendered_options = ",\n".join(option_sql(name, value) for name, value in options)
    return f"ATTACH {sql_literal(target.warehouse)} AS {target.attach_as} (\n{rendered_options}\n);"


def table_basename(variant_name: str, size: BenchmarkSize, repetition: int) -> str:
    table = f"bench_{variant_name}_{size.label}_r{repetition}".lower()
    return re.sub(r"[^a-z0-9_]", "_", table)


def relation_name(
    target: CatalogTarget,
    variant_name: str,
    size: BenchmarkSize,
    repetition: int,
    suffix: str | None = None,
) -> str:
    table = table_basename(variant_name, size, repetition)
    if suffix:
        table = f"{table}_{suffix}"
    return f"{target.attach_as}.{target.default_schema}.{table}"


def create_table_sql(
    target: CatalogTarget,
    variant_name: str,
    size: BenchmarkSize,
    repetition: int,
    relation: str,
    columns: str,
) -> str:
    statement = f"CREATE TABLE {relation} ({columns})"
    if target.table_location_root:
        table_location = (
            f"{target.table_location_root.rstrip('/')}/"
            f"{table_basename(variant_name, size, repetition)}/"
        )
        statement += f"\nWITH ('location' = {sql_literal(table_location)})"
    return statement + ";"


def render_crud_workload_sql(
    target: CatalogTarget,
    variant_name: str,
    size: BenchmarkSize,
    repetition: int,
    keep_tables: bool,
) -> str:
    relation = relation_name(target, variant_name, size, repetition)
    expected_remaining_count = size.rows // 2
    expected_remaining_sum = expected_remaining_count**2
    lines = []
    if target.create_schema:
        lines.extend(
            [
                ".print >>> PHASE: create_schema",
                f"CREATE SCHEMA IF NOT EXISTS {target.attach_as}.{target.default_schema};",
                "",
            ]
        )
    lines.extend(
        [
            f".print >>> PHASE: create_table {size.label} rep {repetition}",
            create_table_sql(
                target,
                variant_name,
                size,
                repetition,
                relation,
                "id BIGINT, h BIGINT, label VARCHAR",
            ),
            "",
            f".print >>> PHASE: insert {size.label} rep {repetition}",
            f"INSERT INTO {relation}",
            "SELECT",
            "  i AS id,",
            "  (i * 2654435761 % 1000000007)::BIGINT AS h,",
            "  ('payload ' || i)::VARCHAR AS label",
            f"FROM range({size.rows}) AS t(i);",
            "",
            f".print >>> PHASE: readback {size.label} rep {repetition}",
            "SELECT count(*) AS row_count, sum(id) AS id_sum,",
            "       count(*) FILTER (WHERE id % 10 = 0) AS decile_rows",
            f"FROM {relation};",
            "",
            f".print >>> PHASE: delete {size.label} rep {repetition}",
            f"DELETE FROM {relation} WHERE id % 2 = 0;",
            "",
            f".print >>> PHASE: read_after_delete {size.label} rep {repetition}",
            "SELECT",
            "  CASE",
            f"    WHEN count(*) = {expected_remaining_count}",
            f"     AND COALESCE(sum(id), 0) = {expected_remaining_sum}",
            "     AND count(*) FILTER (WHERE id % 2 = 0) = 0",
            "    THEN count(*)",
            "    ELSE error('delete verification failed')",
            "  END AS remaining_rows,",
            "  COALESCE(sum(id), 0) AS remaining_id_sum,",
            "  count(*) FILTER (WHERE id % 2 = 0) AS even_rows_remaining",
            f"FROM {relation};",
            "",
        ]
    )
    if not keep_tables:
        lines.extend(
            [
                f".print >>> PHASE: cleanup {size.label} rep {repetition}",
                f"DROP TABLE IF EXISTS {relation};",
                "",
            ]
        )
    return "\n".join(lines)


def render_tpch_read_workload_sql(
    target: CatalogTarget,
    variant_name: str,
    size: BenchmarkSize,
    repetition: int,
    keep_tables: bool,
) -> str:
    if size.scale_factor is None:
        raise ValueError("tpch-read workload requires a scale factor")

    lineitem = relation_name(target, variant_name, size, repetition, "lineitem")
    orders = relation_name(target, variant_name, size, repetition, "orders")
    customer = relation_name(target, variant_name, size, repetition, "customer")
    generated_tables = {
        "lineitem": lineitem,
        "orders": orders,
        "customer": customer,
    }
    lines = []
    if target.create_schema:
        lines.extend(
            [
                ".print >>> PHASE: create_schema",
                f"CREATE SCHEMA IF NOT EXISTS {target.attach_as}.{target.default_schema};",
                "",
            ]
        )
    lines.extend(
        [
            f".print >>> PHASE: tpch_generate {size.label} rep {repetition}",
            "INSTALL tpch;",
            "LOAD tpch;",
            f"CALL dbgen(sf={size.scale_factor:g});",
            "",
            f".print >>> PHASE: tpch_load {size.label} rep {repetition}",
        ]
    )
    for local_table, catalog_table in generated_tables.items():
        lines.append(f"DROP TABLE IF EXISTS {catalog_table};")
        lines.append(f"CREATE TABLE {catalog_table} AS SELECT * FROM {local_table};")
    lines.extend(
        [
            "",
            f".print >>> PHASE: tpch_q01 {size.label} rep {repetition}",
            "SELECT",
            "  l_returnflag,",
            "  l_linestatus,",
            "  sum(l_quantity) AS sum_qty,",
            "  sum(l_extendedprice) AS sum_base_price,",
            "  sum(l_extendedprice * (1 - l_discount)) AS sum_disc_price,",
            "  count(*) AS count_order",
            f"FROM {lineitem}",
            "WHERE l_shipdate <= DATE '1998-09-02'",
            "GROUP BY l_returnflag, l_linestatus",
            "ORDER BY l_returnflag, l_linestatus;",
            "",
            f".print >>> PHASE: tpch_q03 {size.label} rep {repetition}",
            "SELECT",
            "  l_orderkey,",
            "  sum(l_extendedprice * (1 - l_discount)) AS revenue,",
            "  o_orderdate,",
            "  o_shippriority",
            f"FROM {customer}",
            f"JOIN {orders} ON c_custkey = o_custkey",
            f"JOIN {lineitem} ON l_orderkey = o_orderkey",
            "WHERE c_mktsegment = 'BUILDING'",
            "  AND o_orderdate < DATE '1995-03-15'",
            "  AND l_shipdate > DATE '1995-03-15'",
            "GROUP BY l_orderkey, o_orderdate, o_shippriority",
            "ORDER BY revenue DESC, o_orderdate",
            "LIMIT 10;",
            "",
            f".print >>> PHASE: tpch_q06 {size.label} rep {repetition}",
            "SELECT sum(l_extendedprice * l_discount) AS revenue",
            f"FROM {lineitem}",
            "WHERE l_shipdate >= DATE '1994-01-01'",
            "  AND l_shipdate < DATE '1995-01-01'",
            "  AND l_discount BETWEEN 0.05 AND 0.07",
            "  AND l_quantity < 24;",
            "",
        ]
    )
    if not keep_tables:
        lines.append(f".print >>> PHASE: cleanup {size.label} rep {repetition}")
        for catalog_table in generated_tables.values():
            lines.append(f"DROP TABLE IF EXISTS {catalog_table};")
        lines.append("")
    return "\n".join(lines)


def render_workload_sql(
    target: CatalogTarget,
    variant_name: str,
    size: BenchmarkSize,
    repetition: int,
    keep_tables: bool,
    workload: str = "crud",
) -> str:
    if workload == "crud":
        return render_crud_workload_sql(target, variant_name, size, repetition, keep_tables)
    if workload == "tpch-read":
        return render_tpch_read_workload_sql(target, variant_name, size, repetition, keep_tables)
    raise ValueError(f"unknown workload: {workload}")


def artifact_stem(
    target: CatalogTarget,
    variant: AttachVariant,
    size: BenchmarkSize,
    repetition: int,
    workload: str,
) -> str:
    stem = f"{target.name}_{variant.name}_{size.label}_r{repetition}"
    if workload != "crud":
        safe_workload = workload.replace("-", "_")
        stem = f"{target.name}_{safe_workload}_{variant.name}_{size.label}_r{repetition}"
    return stem


def render_run_sql(
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
) -> tuple[str, Path]:
    stem = artifact_stem(target, variant, size, repetition, workload)
    http_log_path = output_dir / f"http_{stem}.csv"
    profile_sql = ""
    if profile:
        profile_path = output_dir / f"profile_{stem}.json"
        profile_sql = "\n".join(
            [
                "PRAGMA enable_profiling='json';",
                f"PRAGMA profiling_output={sql_literal(str(profile_path))};",
            ]
        )
    sql = RUN_TEMPLATE.read_text().format(
        threads=threads,
        memory_limit=memory_limit,
        aws_load_sql="LOAD aws;" if target.aws_secret else "",
        profile_sql=profile_sql,
        secret_sql=render_secret_sql(target, env),
        attach_sql=render_attach_sql(target, env, variant),
        workload_sql=render_workload_sql(
            target, variant.name, size, repetition, keep_tables, workload
        ),
        http_log_path=http_log_path,
    )
    return sql, http_log_path
