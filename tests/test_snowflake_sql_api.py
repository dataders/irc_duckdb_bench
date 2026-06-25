"""Tests for Snowflake/Horizon helper env-file integration."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "snowflake_sql_api.py"


def load_module():
    spec = importlib.util.spec_from_file_location("snowflake_sql_api", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SnowflakeSqlApiEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.helper = load_module()

    def test_load_configured_env_reads_private_profile_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "irc-duckdb-bench.envrc"
            env_path.write_text('export HORIZON_SCHEMA="AWS_CLOUD_COST"\n')

            with patch.dict(
                os.environ,
                {
                    "IRC_DUCKDB_BENCH_ENV_FILE": str(env_path),
                },
                clear=False,
            ):
                os.environ.pop("HORIZON_SCHEMA", None)

                self.assertTrue(self.helper.load_configured_env())

                self.assertEqual(os.environ["HORIZON_SCHEMA"], "AWS_CLOUD_COST")

    def test_refresh_horizon_token_writes_private_profile_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "irc-duckdb-bench.envrc"
            env_path.write_text("export HORIZON_ACCESS_TOKEN='old-token'\n")

            with (
                patch.dict(os.environ, {"IRC_DUCKDB_BENCH_ENV_FILE": str(env_path)}),
                patch.object(
                    self.helper,
                    "request_horizon_access_token",
                    return_value=("new-token", 60),
                ),
                patch.object(self.helper.time, "time", return_value=1_000),
            ):
                self.helper.refresh_horizon_token()

            text = env_path.read_text()
            self.assertIn("export HORIZON_ACCESS_TOKEN='new-token'", text)
            self.assertIn("export HORIZON_ACCESS_TOKEN_EXPIRES_AT='1060'", text)
            self.assertNotIn("old-token", text)


if __name__ == "__main__":
    unittest.main()
