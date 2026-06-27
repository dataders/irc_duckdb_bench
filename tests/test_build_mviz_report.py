"""Tests for the mviz report generator."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_mviz_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_mviz_report", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BuildMvizReportTest(unittest.TestCase):
    def setUp(self):
        self.report = load_module()

    def test_build_writes_catalog_engine_and_remote_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parquet_path = root / "results.parquet"
            markdown_path = root / "report.md"
            html_path = root / "report.html"
            data_dir = root / "data"
            rows = []
            for size, input_rows in (("tiny", 4), ("large", 10_000_000)):
                for catalog in self.report.CATALOG_ORDER:
                    for engine in self.report.ENGINE_ORDER:
                        rows.append(
                            {
                                "catalog": catalog,
                                "engine": engine,
                                "size": size,
                                "rows": input_rows,
                                "passed": True,
                                "operation_s": 1.0
                                + self.report.CATALOG_ORDER.index(catalog)
                                + self.report.ENGINE_ORDER.index(engine),
                            }
                        )
            pq.write_table(pa.Table.from_pylist(rows), parquet_path)

            self.report.build(
                parquet_path=parquet_path,
                markdown_path=markdown_path,
                html_path=html_path,
                data_dir=data_dir,
                render=False,
            )

            markdown = markdown_path.read_text()
            catalog_section = json.loads((data_dir / "sections" / "catalog.json").read_text())
            engine_section = json.loads((data_dir / "sections" / "engine.json").read_text())
            remote_section = json.loads((data_dir / "sections" / "remote.json").read_text())

        self.assertIn("Performance Across Data Sizes By Catalog", catalog_section["content"])
        self.assertIn("Performance Across Data Sizes By Query Engine", engine_section["content"])
        self.assertIn("Remote Catalog Comparison", remote_section["content"])
        self.assertIn("file=data/by-catalog/aws-glue.json", markdown)
        self.assertIn("file=data/by-engine/duckdb.json", markdown)
        self.assertIn("file=data/remote-comparison/remote-catalog-table.json", markdown)
        self.assertIn("line size=[16,8]", markdown)
        self.assertFalse(html_path.exists())

    def test_remote_table_calculates_ratios_against_polaris(self):
        rows = [
            {
                "size": "tiny",
                "engine": "duckdb",
                "catalog": "polaris_remote",
                "operation_s": 2,
            },
            {"size": "tiny", "engine": "duckdb", "catalog": "horizon", "operation_s": 8},
            {
                "size": "tiny",
                "engine": "duckdb",
                "catalog": "aws_s3_tables",
                "operation_s": 4,
            },
        ]

        table = self.report.remote_table(rows)

        self.assertEqual(table["data"][0]["horizon_vs_polaris"], 4.0)
        self.assertEqual(table["data"][0]["s3_tables_vs_polaris"], 2.0)
        self.assertEqual(table["data"][0]["fastest"], "Polaris remote")


if __name__ == "__main__":
    unittest.main()
