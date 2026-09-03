#!/usr/bin/env python3
"""Static and command-output secret guards for the WorkBuddy overlay."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "floeva_auth_secret_guard", ROOT / "scripts" / "floeva-auth.py"
)
assert SPEC and SPEC.loader
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class SecretOutputGuardTest(unittest.TestCase):
    def test_workbuddy_skill_never_instructs_direct_credential_or_http_access(self) -> None:
        skill = (ROOT / "workbuddy" / "cn" / "skill-overlay.md").read_text(encoding="utf-8")
        forbidden = (
            "ACCESS_TOKEN=$(",
            "config.json",
            "api_key",
            "Authorization:",
            "/open/v1",
            "curl ",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, skill)

    def test_workbuddy_auth_stdout_never_contains_secrets_or_instance_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            AUTH.HOME_DIR = Path(temp)
            profile = AUTH._require_client_profile("floeva-workbuddy-cn")
            paths = AUTH._client_paths(profile)
            AUTH._atomic_write_json(
                paths["instance"],
                {
                    "version": 1,
                    "client_id": "floeva-workbuddy-cn",
                    "client_instance_id": "01234567-89ab-4def-8123-456789abcdef",
                    "created_at": 1_000,
                },
            )
            response = {
                "device_code": "private-device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://floeva.cn/authorize",
                "verification_uri_complete": "https://floeva.cn/authorize?user_code=ABCD-EFGH",
                "expires_in": 600,
                "interval": 5,
            }
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(AUTH, "_request_json", return_value=(200, response)):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = AUTH.main([
                        "floeva-auth.py", "start", "--client", "floeva-workbuddy-cn", "--region", "cn"
                    ])
            output = stdout.getvalue() + stderr.getvalue()
            self.assertEqual(0, result)
            self.assertEqual("https://floeva.cn/authorize?user_code=ABCD-EFGH\n", stdout.getvalue())
            for secret in ("private-device-code", "01234567-89ab-4def-8123-456789abcdef"):
                self.assertNotIn(secret, output)
            session = json.loads(paths["session"].read_text(encoding="utf-8"))
            self.assertEqual("private-device-code", session["device_code"])


if __name__ == "__main__":
    unittest.main()
