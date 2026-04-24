#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "rpi5" / "rpi5-install" / "usr" / "local" / "bin" / "perf-dashboard.py"
SPEC = importlib.util.spec_from_file_location("perf_dashboard", MODULE_PATH)
perf_dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(perf_dashboard)


class PerfDashboardParsingTests(unittest.TestCase):
    def test_extract_tcp_sum_received(self):
        metrics = perf_dashboard.extract_iperf3_metrics({
            "end": {
                "sum_received": {"bits_per_second": 12500000},
                "sum_sent": {"bits_per_second": 13000000},
            }
        })
        self.assertEqual(metrics["tcp_mbps"], 12.5)
        self.assertIsNone(metrics["udp_mbps"])

    def test_extract_udp_sum(self):
        metrics = perf_dashboard.extract_iperf3_metrics({
            "end": {
                "sum": {
                    "bits_per_second": 4100000,
                    "jitter_ms": 1.23456,
                    "lost_percent": 0.55,
                }
            }
        })
        self.assertEqual(metrics["udp_mbps"], 4.1)
        self.assertEqual(metrics["jitter_ms"], 1.235)
        self.assertEqual(metrics["loss_pct"], 0.55)

    def test_extract_falls_back_to_streams(self):
        metrics = perf_dashboard.extract_iperf3_metrics({
            "end": {
                "streams": [
                    {"receiver": {"bits_per_second": 10000000}},
                    {"receiver": {"bits_per_second": 15000000}},
                ]
            }
        })
        self.assertEqual(metrics["tcp_mbps"], 25.0)

    def test_session_to_csv_preserves_zero_loss(self):
        label = "fixture-zero-loss"
        with tempfile.TemporaryDirectory() as tmpdir:
            old_sessions_dir = perf_dashboard.SESSIONS_DIR
            try:
                perf_dashboard.SESSIONS_DIR = tmpdir
                session_dir = pathlib.Path(perf_dashboard.SESSIONS_DIR) / label
                session_dir.mkdir(parents=True, exist_ok=True)
                record = {
                    "timestamp": "2026-04-24T12:00:00",
                    "session_label": label,
                    "test_type": "udp_jitter",
                    "source_node": "mesh-a",
                    "destination_node": "mesh-b",
                    "active_interfaces": ["wlan2"],
                    "halow_channel": "5",
                    "halow_bw": "1MHz",
                    "hop_count": 2,
                    "hop_count_source": "batctl",
                    "iperf3_result": {
                        "end": {
                            "sum": {
                                "bits_per_second": 4000000,
                                "jitter_ms": 0.333,
                                "lost_percent": 0.0,
                            }
                        }
                    },
                    "ping_result": {},
                }
                with open(session_dir / "one.json", "w") as f:
                    import json
                    json.dump(record, f)

                csv_text = perf_dashboard.session_to_csv(label)
                self.assertIn(",2,batctl,,4.0,0.333,0.0,", csv_text)
            finally:
                perf_dashboard.SESSIONS_DIR = old_sessions_dir


if __name__ == "__main__":
    unittest.main()
