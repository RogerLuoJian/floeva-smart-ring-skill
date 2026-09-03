#!/usr/bin/env python3
"""WorkBuddy client profile and Device Flow contract tests."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import stat
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "scripts" / "floeva-auth.py"
SPEC = importlib.util.spec_from_file_location("floeva_auth_workbuddy", HELPER_PATH)
assert SPEC and SPEC.loader
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class WorkBuddyAuthorizationModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = Path(self.temp_dir.name)
        AUTH.HOME_DIR = self.home
        AUTH.CONFIG_DIR = self.home / ".floeva"
        AUTH.CONFIG_FILE = AUTH.CONFIG_DIR / "config.json"
        AUTH.SESSION_FILE = AUTH.CONFIG_DIR / "device-authorization.json"

    def run_main(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = AUTH.main(["floeva-auth.py", *args])
        return result, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def device_response() -> dict[str, object]:
        return {
            "device_code": "private-workbuddy-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://floeva.cn/authorize",
            "verification_uri_complete": "https://floeva.cn/authorize?user_code=ABCD-EFGH",
            "expires_in": 600,
            "interval": 5,
        }

    def test_profile_is_allowlisted_and_uses_dedicated_paths(self) -> None:
        profile = AUTH._require_client_profile("floeva-workbuddy-cn")

        self.assertEqual(("cn",), profile["regions"])
        self.assertEqual("https://server.floeva.cn/ring/api", profile["base_urls"]["cn"])
        self.assertEqual("floeva.cn", profile["verification_hosts"]["cn"])
        paths = AUTH._client_paths(profile)
        self.assertEqual(
            self.home / ".floeva" / "workbuddy" / "floeva-workbuddy-cn" / "instance.json",
            paths["instance"],
        )
        self.assertNotEqual(AUTH.CONFIG_FILE, paths["credential"])
        with self.assertRaises(AUTH.CliError):
            AUTH._require_client_profile("attacker-client")

    def test_init_is_stable_private_and_never_prints_instance_id(self) -> None:
        generated = uuid.UUID("01234567-89ab-4def-8123-456789abcdef")
        with mock.patch.object(AUTH.uuid, "uuid4", return_value=generated) as random_uuid:
            first = self.run_main("init", "--client", "floeva-workbuddy-cn")
            second = self.run_main("init", "--client", "floeva-workbuddy-cn")

        self.assertEqual((0, "initialized\n", ""), first)
        self.assertEqual((0, "initialized\n", ""), second)
        random_uuid.assert_called_once_with()
        profile = AUTH._require_client_profile("floeva-workbuddy-cn")
        instance_path = AUTH._client_paths(profile)["instance"]
        payload = json.loads(instance_path.read_text(encoding="utf-8"))
        self.assertEqual(str(generated), payload["client_instance_id"])
        self.assertEqual(0o600, stat.S_IMODE(instance_path.stat().st_mode))
        self.assertNotIn(str(generated), first[1] + first[2] + second[1] + second[2])

    def test_start_and_complete_bind_the_same_instance(self) -> None:
        instance_id = "01234567-89ab-4def-8123-456789abcdef"
        with mock.patch.object(AUTH.uuid, "uuid4", return_value=uuid.UUID(instance_id)):
            self.assertEqual(0, self.run_main("init", "--client", "floeva-workbuddy-cn")[0])

        start_request = mock.Mock(return_value=(200, self.device_response()))
        with mock.patch.object(AUTH, "_request_json", start_request):
            with mock.patch.object(AUTH.time, "time", return_value=1_000):
                result, stdout, stderr = self.run_main(
                    "start", "--client", "floeva-workbuddy-cn", "--region", "cn"
                )

        self.assertEqual((0, "https://floeva.cn/authorize?user_code=ABCD-EFGH\n", ""),
                         (result, stdout, stderr))
        self.assertNotIn(instance_id, stdout + stderr)
        request_payload = start_request.call_args.args[1]
        self.assertEqual(instance_id, request_payload["client_instance_id"])
        self.assertEqual("floeva-workbuddy-cn", request_payload["client_id"])

        complete_request = mock.Mock(
            return_value=(
                200,
                {
                    "access_token": "private-workbuddy-token",
                    "token_type": "Bearer",
                    "scope": "health:read",
                    "expires_in": 7_776_000,
                },
            )
        )
        with mock.patch.object(AUTH, "_request_json", complete_request):
            with mock.patch.object(AUTH.time, "time", return_value=1_006):
                result, stdout, stderr = self.run_main(
                    "complete", "--client", "floeva-workbuddy-cn"
                )

        self.assertEqual((0, "authorized\n", ""), (result, stdout, stderr))
        exchange_payload = complete_request.call_args.args[1]
        self.assertEqual(instance_id, exchange_payload["client_instance_id"])
        profile = AUTH._require_client_profile("floeva-workbuddy-cn")
        credential = json.loads(
            AUTH._client_paths(profile)["credential"].read_text(encoding="utf-8")
        )
        self.assertEqual(instance_id, credential["client_instance_id"])
        self.assertEqual("floeva-workbuddy-cn", credential["client_id"])
        self.assertNotIn("private-workbuddy-token", stdout + stderr)

    def test_status_is_read_only_and_emits_only_stable_state(self) -> None:
        profile = AUTH._require_client_profile("floeva-workbuddy-cn")
        paths = AUTH._client_paths(profile)
        before = list(self.home.rglob("*"))
        result = self.run_main("status", "--client", "floeva-workbuddy-cn")
        after = list(self.home.rglob("*"))

        self.assertEqual((1, "missing\n", ""), result)
        self.assertEqual(before, after)
        self.assertFalse(paths["root"].exists())

    def test_workbuddy_rejects_global_region_and_legacy_cli_still_works(self) -> None:
        result, _, stderr = self.run_main(
            "start", "--client", "floeva-workbuddy-cn", "--region", "global"
        )
        self.assertEqual(1, result)
        self.assertIn("not available", stderr)

        with mock.patch.object(AUTH, "_request_json", return_value=(200, self.device_response())):
            result, _, _ = self.run_main("start", "cn")
        self.assertEqual(0, result)

    def test_workbuddy_rejects_unbounded_polling_contract(self) -> None:
        response = self.device_response()
        response["interval"] = AUTH.MAX_POLL_INTERVAL_SECONDS + 1
        with mock.patch.object(AUTH, "_request_json", return_value=(200, response)):
            result, _, stderr = self.run_main(
                "start", "--client", "floeva-workbuddy-cn", "--region", "cn"
            )

        self.assertEqual(1, result)
        self.assertIn("invalid authorization polling contract", stderr)


if __name__ == "__main__":
    unittest.main()
