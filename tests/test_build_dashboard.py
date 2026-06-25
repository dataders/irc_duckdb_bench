"""Tests for the benchmark dashboard generator."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_dashboard.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_dashboard", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BuildDashboardTest(unittest.TestCase):
    def setUp(self):
        self.dashboard = load_module()

    def test_normalize_phase_strips_size_and_repetition_suffix(self):
        self.assertEqual(self.dashboard.normalize_phase("create_table tiny rep 2"), "create_table")
        self.assertEqual(self.dashboard.normalize_phase("readback small rep 1"), "readback")
        self.assertEqual(
            self.dashboard.normalize_phase("read_after_delete small rep 3"),
            "read_after_delete",
        )
        self.assertEqual(self.dashboard.normalize_phase("attach"), "attach")

    def test_build_dashboard_data_embeds_rows_events_and_artifact_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run-1"
            target_dir = run_root / "lakekeeper_local"
            target_dir.mkdir(parents=True)
            summary = [
                {
                    "target": "lakekeeper_local",
                    "variant": "default",
                    "size": "tiny",
                    "rows": 4,
                    "repetition": 1,
                    "passed": True,
                    "exit_code": 0,
                    "error": "",
                    "timings": {
                        "startup": 0.1,
                        "attach": 0.01,
                        "create_table tiny rep 1": 0.02,
                        "insert tiny rep 1": 0.03,
                        "readback tiny rep 1": 0.04,
                    },
                    "http_request_count": 1,
                    "http_duration_ms": 12,
                    "http_groups": {"rest_config": {"count": 1, "duration_ms": 12}},
                    "http_phase_groups": {
                        "attach": {"rest_config": {"count": 1, "duration_ms": 12}}
                    },
                    "http_debug_path": "http_debug_lakekeeper_local_default_tiny_r1.jsonl",
                }
            ]
            (target_dir / "summary.json").write_text(json.dumps(summary))
            (target_dir / "summary.csv").write_text("target\nlakekeeper_local\n")
            (target_dir / "lakekeeper_local_default_tiny_r1.sql").write_text("select 1;\n")
            (target_dir / "lakekeeper_local_default_tiny_r1.out").write_text("ok\n")
            (target_dir / "http_lakekeeper_local_default_tiny_r1.csv").write_text("name\n")
            (target_dir / "http_debug_lakekeeper_local_default_tiny_r1.jsonl").write_text(
                json.dumps(
                    {
                        "duration_ms": 12,
                        "host": "catalog.example",
                        "method": "GET",
                        "path": "/v1/config",
                        "phase": "attach",
                        "status": "OK_200",
                        "url_group": "rest_config",
                    }
                )
                + "\n"
            )

            output_path = root / "reports" / "run-1-dashboard.html"
            data = self.dashboard.build_dashboard_data(run_root, output_path)

        self.assertEqual(data["run_id"], "run-1")
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(len(data["events"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["workload_wall_s"], 0.09)
        self.assertEqual(row["support_wall_s"], 0.11)
        self.assertEqual(row["phase_timings"]["create_table"], 0.02)
        self.assertIn("sql", row["artifact_links"])
        self.assertEqual(data["events"][0]["normalized_phase"], "attach")
        self.assertEqual(data["events"][0]["url_group"], "rest_config")

    def test_render_html_uses_multi_target_picker(self):
        data = {
            "run_id": "run-1",
            "generated_at": "2026-06-25T00:00:00+00:00",
            "run_root": ".tmp/catalog_benchmarks/run-1",
            "rows": [],
            "events": [],
            "artifacts": [],
            "targets": ["lakekeeper_local", "polaris_local"],
            "sizes": ["tiny"],
            "variants": ["default"],
            "http_groups": [],
            "phase_order": list(self.dashboard.PHASE_ORDER),
            "workload_phases": list(self.dashboard.WORKLOAD_PHASES),
            "support_phases": list(self.dashboard.SUPPORT_PHASES),
            "target_labels": self.dashboard.TARGET_LABELS,
            "http_group_labels": self.dashboard.HTTP_GROUP_LABELS,
        }

        html = self.dashboard.render_html(data)

        self.assertIn('id="targetPicker"', html)
        self.assertIn('id="targetPickerMenu"', html)
        self.assertIn('id="attributionChart"', html)
        self.assertIn('id="attributionTable"', html)
        self.assertIn("state.targets", html)
        self.assertNotIn('id="targetFilter"', html)


if __name__ == "__main__":
    unittest.main()
