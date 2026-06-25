"""Regression tests for keeping this repo standalone."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StandaloneProjectTest(unittest.TestCase):
    def test_project_metadata_uses_standalone_name(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

        self.assertEqual(pyproject["project"]["name"], "irc-duckdb-bench")

    def test_user_facing_files_do_not_retain_source_repo_names(self) -> None:
        paths = [
            ROOT / ".env.example",
            ROOT / "README.md",
            ROOT / "docs" / "catalog-benchmarks.md",
            ROOT / "scripts" / "snowflake_sql_api.py",
            ROOT / "scripts" / "start_local_polaris.sh",
            ROOT / "scripts" / "stop_local_polaris.sh",
        ]

        forbidden = [
            "dbt_aws_cloud_cost",
            "dbt-aws-cloud-cost",
            "DBT_AWS_CLOUD_COST",
            "dbt multi-catalog demo",
        ]

        for path in paths:
            with self.subTest(path=path):
                text = path.read_text()
                for token in forbidden:
                    self.assertNotIn(token, text)

    def test_env_example_is_benchmark_focused(self) -> None:
        env_example = (ROOT / ".env.example").read_text()

        self.assertIn("DUCKDB_CLI=", env_example)
        self.assertIn("HORIZON_ACCESS_TOKEN=", env_example)
        self.assertNotIn("DBT_BIN=", env_example)

    def test_envrc_uses_dotfiles_env_profile(self) -> None:
        envrc = (ROOT / ".envrc").read_text()

        self.assertIn("IRC_DUCKDB_BENCH_ENV_FILE", envrc)
        self.assertIn("source_dotfiles_env irc-duckdb-bench", envrc)
        self.assertNotIn("source_dotfiles_env polaris", envrc)
        self.assertNotIn("source_dotfiles_env snowflake", envrc)

    def test_local_polaris_scripts_use_standalone_compose_project(self) -> None:
        for name in ["start_local_polaris.sh", "stop_local_polaris.sh"]:
            script = (ROOT / "scripts" / name).read_text()
            with self.subTest(script=name):
                self.assertIn("irc-duckdb-bench-polaris", script)


if __name__ == "__main__":
    unittest.main()
