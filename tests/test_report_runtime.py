#!/usr/bin/env python3
"""Behavior and security tests for the Floeva Health Canvas runtime."""

from __future__ import annotations

import importlib.util
import http.client
import json
import os
import stat
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "scripts" / "floeva-report.py"
SPEC = importlib.util.spec_from_file_location("floeva_report", RUNTIME_PATH)
assert SPEC and SPEC.loader
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def health_payload() -> dict[str, object]:
    return {
        "code": 200,
        "data": {
            "steps_7d": {
                "summary": {"total_steps": 12_000, "avg_steps_per_day": "6000"},
                "data": [
                    {"date": "2026-08-14", "steps": 5_000},
                    {"date": "2026-08-15", "steps": 7_000},
                ],
            },
            "heart_rate_7d": {
                "data": [
                    {
                        "date": "2026-08-15",
                        "min_heart_rate": 58,
                        "avg_heart_rate": "68",
                        "max_heart_rate": 84,
                        "sample_count": 12,
                    }
                ]
            },
            "last_sleep": {
                "data": [
                    {
                        "date": "2026-08-15",
                        "total_minutes": 430,
                        "deep_sleep_minutes": 80,
                        "rem_sleep_minutes": 90,
                        "light_sleep_minutes": 260,
                    }
                ]
            },
            "daily_summary": {
                "data": [
                    {
                        "date": "2026-08-15",
                        "stress_recovery": {"avg_hrv": 48, "resting_hr": 57},
                    }
                ]
            },
            "baseline": {"is_personalized": True, "days_of_data": 28},
        },
    }


class ReportRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = Path(self.temp_dir.name)
        REPORT.CONFIG_DIR = self.home / ".floeva"
        REPORT.CONFIG_FILE = REPORT.CONFIG_DIR / "config.json"
        REPORT.REPORTS_DIR = REPORT.CONFIG_DIR / "reports"

    def test_prepare_stages_only_health_data_with_private_permissions(self) -> None:
        result = REPORT.prepare_report(health_payload(), "cn", now=1_000)

        self.assertRegex(result["session"], r"^[A-Za-z0-9_-]{32}$")
        self.assertEqual(
            f"http://127.0.0.1:5176/report/{result['session']}/",
            result["url"],
        )
        self.assertEqual(7_000, result["summary"]["latest"]["steps"])
        self.assertEqual(48, result["summary"]["latest"]["hrv"])
        session_dir = REPORT.REPORTS_DIR / result["session"]
        report_file = session_dir / "report.json"
        staged = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual("cn", staged["region"])
        self.assertIn("data", staged)
        self.assertNotIn("access_token", staged)
        self.assertNotIn("api_key", staged)
        self.assertEqual(0o700, stat.S_IMODE(REPORT.REPORTS_DIR.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(session_dir.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(report_file.stat().st_mode))

    def test_prepare_rejects_non_success_payload(self) -> None:
        with self.assertRaisesRegex(REPORT.CliError, "temporarily unavailable"):
            REPORT.prepare_report(
                {"code": 500, "msg": "temporarily unavailable"}, "global", now=1_000
            )

    def test_cleanup_removes_only_expired_valid_sessions(self) -> None:
        expired = REPORT.prepare_report(health_payload(), "global", now=1_000)
        active = REPORT.prepare_report(health_payload(), "global", now=4_000)
        unrelated = REPORT.REPORTS_DIR / "do-not-touch"
        unrelated.mkdir()

        removed = REPORT.cleanup_expired(now=4_601)

        self.assertEqual(1, removed)
        self.assertFalse((REPORT.REPORTS_DIR / expired["session"]).exists())
        self.assertTrue((REPORT.REPORTS_DIR / active["session"]).exists())
        self.assertTrue(unrelated.exists())

    def test_server_exposes_only_scoped_report_and_hardened_headers(self) -> None:
        result = REPORT.prepare_report(health_payload(), "cn", port=0)
        server = REPORT.create_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}/report/{result['session']}/"

        with urllib.request.urlopen(base, timeout=5) as response:
            html = response.read().decode("utf-8")
            self.assertEqual(200, response.status)
            self.assertEqual("no-store", response.headers["Cache-Control"])
            self.assertEqual("no-referrer", response.headers["Referrer-Policy"])
            self.assertEqual("DENY", response.headers["X-Frame-Options"])
            self.assertEqual(
                "same-origin", response.headers["Cross-Origin-Resource-Policy"]
            )
            self.assertIn("camera=()", response.headers["Permissions-Policy"])
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("Floeva Health Canvas", html)

        with urllib.request.urlopen(base + "report.json", timeout=5) as response:
            staged = json.loads(response.read())
            self.assertEqual("cn", staged["region"])
            self.assertNotIn("access_token", staged)

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as response:
            status = json.loads(response.read())
            self.assertEqual("floeva-health-canvas", status["app"])

        with self.assertRaises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/report/{'A' * 32}/report.json",
                timeout=5,
            )
        self.assertEqual(404, missing.exception.code)

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", "/healthz", headers={"Host": "attacker.example"})
        self.assertEqual(421, connection.getresponse().status)

    def test_fetch_uses_bearer_without_staging_credential(self) -> None:
        REPORT.CONFIG_DIR.mkdir(mode=0o700)
        REPORT._atomic_write_json(
            REPORT.CONFIG_FILE,
            {
                "access_token": "private-oauth-token",
                "auth_mode": "device_authorization",
                "base_url": "https://server.floeva.cn/ring/api",
                "expires_at": int(time.time()) + 3_600,
                "region": "cn",
            },
        )
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = json.dumps(
            health_payload()
        ).encode("utf-8")
        opener = mock.Mock()
        opener.open.return_value = response

        with mock.patch.object(REPORT.urllib.request, "build_opener", return_value=opener):
            payload, region = REPORT._fetch_health_overview()

        request = opener.open.call_args.args[0]
        self.assertEqual("Bearer private-oauth-token", request.get_header("Authorization"))
        self.assertEqual("cn", region)
        result = REPORT.prepare_report(payload, region)
        staged = (REPORT.REPORTS_DIR / result["session"] / "report.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("private-oauth-token", staged)

    def test_frontend_is_local_original_runtime_without_inline_code(self) -> None:
        index = (REPORT.ASSET_DIR / "index.html").read_text(encoding="utf-8")
        script = (REPORT.ASSET_DIR / "app.js").read_text(encoding="utf-8")
        stylesheet = (REPORT.ASSET_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn("Floeva Health Canvas", index)
        self.assertIn('src="./app.js"', index)
        self.assertIn('href="./app.css"', index)
        self.assertNotIn("<style", index)
        self.assertNotIn("<script>", index)
        self.assertIn('fetch("./report.json"', script)
        self.assertNotIn("access_token", script)
        self.assertNotIn("api_key", script)
        self.assertNotIn("https://", index + script + stylesheet)
        self.assertIn("--accent: #7c3aed", stylesheet)
        self.assertIn("#f5d9b8", stylesheet)
        for font_name in ("Inter-Regular.ttf", "Inter-Bold.ttf"):
            signature = (REPORT.ASSET_DIR / "fonts" / font_name).read_bytes()[:4]
            self.assertIn(signature, (b"OTTO", b"\x00\x01\x00\x00"))


if __name__ == "__main__":
    unittest.main()
