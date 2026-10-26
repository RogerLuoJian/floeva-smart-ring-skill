#!/usr/bin/env python3
"""Declared Agent authorization isolation contracts."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "floeva_agent_authorization", ROOT / "scripts" / "floeva-auth.py"
)
assert SPEC and SPEC.loader
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)
REPORT_SPEC = importlib.util.spec_from_file_location(
    "floeva_agent_report", ROOT / "scripts" / "floeva-report.py"
)
assert REPORT_SPEC and REPORT_SPEC.loader
REPORT = importlib.util.module_from_spec(REPORT_SPEC)
REPORT_SPEC.loader.exec_module(REPORT)


class AgentAuthorizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        AUTH.HOME_DIR = Path(self.temp_dir.name)
        AUTH.CONFIG_DIR = AUTH.HOME_DIR / ".floeva"
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
            "device_code": "private-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://getfloeva.com/authorize",
            "verification_uri_complete": "https://getfloeva.com/authorize?user_code=ABCD-EFGH",
            "expires_in": 600,
            "interval": 5,
        }

    def test_names_are_hashed_isolated_and_do_not_use_legacy_config(self) -> None:
        codex = AUTH._agent_profile("Codex")
        claude = AUTH._agent_profile("Claude")
        codex_paths = AUTH._client_paths(codex)
        claude_paths = AUTH._client_paths(claude)
        self.assertNotEqual(codex_paths["root"], claude_paths["root"])
        self.assertEqual(AUTH.HOME_DIR / ".floeva" / "agents", codex_paths["root"].parent)
        self.assertNotIn("Codex", str(codex_paths["root"]))
        self.assertNotEqual(AUTH.CONFIG_FILE, codex_paths["credential"])

        with mock.patch.object(AUTH.uuid, "uuid4", return_value=uuid.UUID("01234567-89ab-4def-8123-456789abcdef")):
            with mock.patch.object(AUTH, "_request_json", return_value=(200, self.device_response())) as request:
                result = self.run_main("start", "--agent-name", "Codex", "--region", "global")

        self.assertEqual(0, result[0])
        payload = request.call_args.args[1]
        self.assertEqual(AUTH.LEGACY_CLIENT_ID, payload["client_id"])
        self.assertEqual("Codex", payload["agent_name"])
        self.assertIn("client_instance_id", payload)
        self.assertTrue(codex_paths["session"].is_file())
        self.assertFalse(AUTH.CONFIG_FILE.exists())
        identity = json.loads(codex_paths["instance"].read_text(encoding="utf-8"))
        self.assertEqual("Codex", identity["agent_name"])

    def test_complete_binds_credential_to_the_declared_agent(self) -> None:
        with mock.patch.object(AUTH, "_request_json", return_value=(200, self.device_response())):
            with mock.patch.object(AUTH.time, "time", return_value=1_000):
                self.assertEqual(0, self.run_main("start", "--agent-name", "Codex", "--region", "global")[0])
        response = (200, {"access_token": "private-token", "token_type": "Bearer", "scope": "health:read", "expires_in": 3600})
        with mock.patch.object(AUTH, "_request_json", return_value=response):
            with mock.patch.object(AUTH.time, "time", return_value=1_006):
                result = self.run_main("complete", "--agent-name", "Codex")
        self.assertEqual((0, "authorized\n", ""), result)
        profile = AUTH._agent_profile("Codex")
        credential = json.loads(AUTH._client_paths(profile)["credential"].read_text(encoding="utf-8"))
        self.assertEqual("Codex", credential["agent_name"])
        self.assertNotIn("private-token", result[1] + result[2])
        self.assertEqual((1, "missing\n", ""), self.run_main("status", "--agent-name", "Claude"))

    def test_rejects_control_bidi_and_client_name_mix(self) -> None:
        for name in ("Co\ndex", "Codex\u202e"):
            with self.subTest(name=name):
                result = self.run_main("status", "--agent-name", name)
                self.assertEqual(1, result[0])
                self.assertIn("Agent name", result[2])
        with self.assertRaisesRegex(AUTH.CliError, "Agent name"):
            AUTH._agent_profile("")
        result = self.run_main("status", "--client", "floeva-workbuddy-cn", "--agent-name", "Codex")
        self.assertEqual(1, result[0])
        self.assertIn("either --agent-name or --client", result[2])

    def test_report_scope_never_falls_back_to_legacy_config(self) -> None:
        REPORT.CONFIG_DIR = AUTH.CONFIG_DIR
        REPORT.CONFIG_FILE = AUTH.CONFIG_FILE
        AUTH._atomic_write_json(
            AUTH.CONFIG_FILE,
            {
                "access_token": "legacy-token",
                "base_url": "https://us.getfloeva.com/ring/api",
                "expires_at": 9_999_999_999,
                "region": "global",
            },
        )
        agent_file = REPORT._agent_credential_file("Codex")
        with self.assertRaisesRegex(REPORT.CliError, "missing"):
            REPORT._load_config(agent_file, "Codex")
        AUTH._atomic_write_json(
            agent_file,
            {
                "access_token": "agent-token",
                "base_url": "https://us.getfloeva.com/ring/api",
                "expires_at": 9_999_999_999,
                "region": "global",
                "agent_name": "Codex",
            },
        )
        self.assertEqual(
            ("agent-token", "https://us.getfloeva.com/ring/api", "global"),
            REPORT._load_config(agent_file, "Codex"),
        )

    def test_data_commands_read_only_the_matching_agent_scope(self) -> None:
        profile = AUTH._agent_profile("Codex")
        paths = AUTH._client_paths(profile)
        instance_id = "01234567-89ab-4def-8123-456789abcdef"
        AUTH._atomic_write_json(
            paths["instance"],
            {
                "version": 1,
                "client_id": AUTH.LEGACY_CLIENT_ID,
                "client_instance_id": instance_id,
                "agent_name": "Codex",
                "created_at": 1_000,
            },
        )
        AUTH._atomic_write_json(
            paths["credential"],
            {
                "access_token": "codex-token",
                "auth_mode": "device_authorization",
                "base_url": "https://us.getfloeva.com/ring/api",
                "expires_at": 9_999_999_999,
                "region": "global",
                "client_id": AUTH.LEGACY_CLIENT_ID,
                "client_instance_id": instance_id,
                "agent_name": "Codex",
            },
        )
        AUTH._atomic_write_json(
            AUTH.CONFIG_FILE,
            {"api_key": "legacy-token", "base_url": "https://server.floeva.cn/ring/api"},
        )
        with mock.patch.object(AUTH, "_request_open_api_json", return_value={"coverageDays": 7}) as request:
            result = self.run_main("overview", "--agent-name", "Codex")
        self.assertEqual((0, '{"coverageDays":7}\n', ""), result)
        self.assertEqual("codex-token", request.call_args.args[0]["access_token"])

    def test_legacy_data_commands_use_only_the_original_config_scope(self) -> None:
        AUTH._atomic_write_json(
            AUTH.CONFIG_FILE,
            {
                "api_key": "legacy-token",
                "base_url": "https://server.floeva.cn/ring/api",
            },
        )
        with mock.patch.object(
            AUTH, "_request_open_api_json", return_value={"coverageDays": 7}
        ) as request:
            result = self.run_main("overview")
        self.assertEqual((0, '{"coverageDays":7}\n', ""), result)
        self.assertEqual("legacy-token", request.call_args.args[0]["access_token"])
        self.assertEqual(
            "https://server.floeva.cn/ring/api", request.call_args.args[0]["base_url"]
        )

        tool = {
            "type": "function",
            "function": {"name": "get_sleep_data", "parameters": {}},
        }
        with mock.patch.object(
            AUTH, "_request_open_api_json", return_value={"tools": [tool]}
        ) as tools_request:
            tools_result = self.run_main("tools")
        self.assertEqual(0, tools_result[0])
        self.assertEqual("legacy-token", tools_request.call_args.args[0]["access_token"])

        AUTH._atomic_write_json(
            AUTH.CONFIG_FILE,
            {
                "access_token": "legacy-oauth-token",
                "auth_mode": "device_authorization",
                "base_url": "https://us.getfloeva.com/ring/api",
                "expires_at": 9_999_999_999,
                "region": "global",
            },
        )
        with mock.patch.object(
            AUTH, "_request_open_api_json", return_value={"coverageDays": 3}
        ) as oauth_request:
            oauth_result = self.run_main("overview")
        self.assertEqual((0, '{"coverageDays":3}\n', ""), oauth_result)
        self.assertEqual(
            "legacy-oauth-token", oauth_request.call_args.args[0]["access_token"]
        )


if __name__ == "__main__":
    unittest.main()
