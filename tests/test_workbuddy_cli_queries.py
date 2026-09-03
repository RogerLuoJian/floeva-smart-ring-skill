#!/usr/bin/env python3
"""WorkBuddy CLI + Skill authorization and health-query contracts."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "floeva_workbuddy_cli", ROOT / "scripts" / "floeva-auth.py"
)
assert SPEC and SPEC.loader
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class WorkBuddyCliQueryTest(unittest.TestCase):
    INSTANCE_ID = "01234567-89ab-4def-8123-456789abcdef"
    TOKEN = "private-workbuddy-token"

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        AUTH.HOME_DIR = Path(self.temp_dir.name)
        self.profile = AUTH._require_client_profile("floeva-workbuddy-cn")
        self.paths = AUTH._client_paths(self.profile)
        AUTH._atomic_write_json(
            self.paths["instance"],
            {
                "version": 1,
                "client_id": "floeva-workbuddy-cn",
                "client_instance_id": self.INSTANCE_ID,
                "created_at": 1_000,
            },
        )

    def run_main(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = AUTH.main(["floeva-auth.py", *args])
        return result, stdout.getvalue(), stderr.getvalue()

    def write_credential(self) -> None:
        AUTH._atomic_write_json(
            self.paths["credential"],
            {
                "access_token": self.TOKEN,
                "auth_mode": "device_authorization",
                "base_url": "https://server.floeva.cn/ring/api",
                "client_id": "floeva-workbuddy-cn",
                "client_instance_id": self.INSTANCE_ID,
                "expires_at": 9_999_999_999,
                "region": "cn",
            },
        )

    @staticmethod
    def tool_definition(name: str) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": "Read Floeva health data.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

    def test_auth_is_one_command_that_prints_url_then_polls_to_completion(self) -> None:
        device_response = {
            "device_code": "private-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://floeva.cn/authorize",
            "verification_uri_complete": "https://floeva.cn/authorize?user_code=ABCD-EFGH",
            "expires_in": 600,
            "interval": 5,
        }
        pending = (400, {"error": "authorization_pending"})
        authorized = (
            200,
            {
                "access_token": self.TOKEN,
                "token_type": "Bearer",
                "scope": "health:read",
                "expires_in": 7_776_000,
            },
        )
        clock = [1_000, 1_000, 1_000, 1_005, 1_005]
        with mock.patch.object(
            AUTH, "_request_json", side_effect=[(200, device_response), pending, authorized]
        ):
            with mock.patch.object(AUTH.time, "time", side_effect=clock):
                result = self.run_main(
                    "auth", "--client", "floeva-workbuddy-cn", "--region", "cn"
                )

        self.assertEqual(
            (0, "https://floeva.cn/authorize?user_code=ABCD-EFGH\nauthorized\n", ""),
            result,
        )
        self.assertNotIn(self.TOKEN, result[1] + result[2])
        self.assertNotIn(self.INSTANCE_ID, result[1] + result[2])

    def test_tools_filters_to_the_read_only_allowlist(self) -> None:
        self.write_credential()
        tools = {
            "tools": [
                self.tool_definition("get_sleep_data"),
                self.tool_definition("delete_account"),
            ]
        }
        with mock.patch.object(AUTH, "_request_open_api_json", return_value=tools):
            result = self.run_main("tools", "--client", "floeva-workbuddy-cn")

        self.assertEqual(0, result[0])
        payload = json.loads(result[1])
        self.assertEqual(
            ["get_sleep_data"],
            [item["function"]["name"] for item in payload["tools"]],
        )
        self.assertNotIn(self.TOKEN, result[1] + result[2])

    def test_call_requires_discovery_and_outputs_only_business_json(self) -> None:
        self.write_credential()
        request = mock.Mock(
            side_effect=[
                {"tools": [self.tool_definition("get_sleep_data")]},
                {"date": "2026-09-02", "sleepMinutes": 420},
            ]
        )
        with mock.patch.object(AUTH, "_request_open_api_json", request):
            result = self.run_main(
                "call",
                "--client",
                "floeva-workbuddy-cn",
                "--tool",
                "get_sleep_data",
                "--arguments",
                '{"days":7}',
            )

        self.assertEqual((0, '{"date":"2026-09-02","sleepMinutes":420}\n', ""), result)
        self.assertEqual(
            {
                "toolName": "get_sleep_data",
                "arguments": {"days": 7},
            },
            request.call_args_list[1].args[2],
        )
        self.assertNotIn(self.TOKEN, result[1] + result[2])

    def test_overview_and_errors_do_not_expose_credentials(self) -> None:
        self.write_credential()
        with mock.patch.object(
            AUTH, "_request_open_api_json", return_value={"coverageDays": 7}
        ):
            result = self.run_main("overview", "--client", "floeva-workbuddy-cn")
        self.assertEqual((0, '{"coverageDays":7}\n', ""), result)

        with mock.patch.object(AUTH, "_request_open_api_json") as request:
            rejected = self.run_main(
                "call",
                "--client",
                "floeva-workbuddy-cn",
                "--tool",
                "delete_account",
                "--arguments",
                "{}",
            )
        self.assertEqual(1, rejected[0])
        self.assertIn("Unsupported Floeva tool", rejected[2])
        request.assert_not_called()
        self.assertNotIn(self.TOKEN, rejected[1] + rejected[2])
        self.assertNotIn(self.INSTANCE_ID, rejected[1] + rejected[2])

    def test_open_api_transport_injects_token_only_into_fixed_https_url(self) -> None:
        self.write_credential()
        credential = AUTH._require_workbuddy_credential(self.profile)
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"code":200,"data":{"coverageDays":7}}'
        opener = mock.Mock()
        opener.open.return_value = response

        with mock.patch.object(AUTH.urllib.request, "build_opener", return_value=opener):
            result = AUTH._request_open_api_json(
                credential, "/open/v1/health/overview"
            )

        self.assertEqual({"coverageDays": 7}, result)
        request = opener.open.call_args.args[0]
        self.assertEqual(
            "https://server.floeva.cn/ring/api/open/v1/health/overview",
            request.full_url,
        )
        self.assertEqual(f"Bearer {self.TOKEN}", request.get_header("Authorization"))
        with self.assertRaisesRegex(AUTH.CliError, "Unsupported Floeva operation"):
            AUTH._request_open_api_json(credential, "https://attacker.example/data")

    def test_open_api_transport_maps_failures_without_leaking_secrets(self) -> None:
        self.write_credential()
        credential = AUTH._require_workbuddy_credential(self.profile)
        cases = (
            (401, "missing or expired", 4),
            (429, "limit reached", 5),
            (500, "temporarily unavailable", 1),
        )
        for status, message, exit_code in cases:
            with self.subTest(status=status):
                error = urllib.error.HTTPError(
                    "https://server.floeva.cn",
                    status,
                    "failure",
                    None,
                    io.BytesIO(b"{}"),
                )
                opener = mock.Mock()
                opener.open.side_effect = error
                with mock.patch.object(
                    AUTH.urllib.request, "build_opener", return_value=opener
                ):
                    with self.assertRaises(AUTH.CliError) as raised:
                        AUTH._request_open_api_json(
                            credential, "/open/v1/health/overview"
                        )
                self.assertEqual(exit_code, raised.exception.exit_code)
                self.assertIn(message, str(raised.exception))
                self.assertNotIn(self.TOKEN, str(raised.exception))
                self.assertNotIn(self.INSTANCE_ID, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
