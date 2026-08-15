#!/usr/bin/env python3
"""Behavior tests for the Floeva web-authorization helper and installer."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "scripts" / "floeva-auth.py"
SPEC = importlib.util.spec_from_file_location("floeva_auth", HELPER_PATH)
assert SPEC and SPEC.loader
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class AuthorizationHelperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = Path(self.temp_dir.name)
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
    def device_response(
        verification_url: str = "https://getfloeva.com/authorize?user_code=ABCD-EFGH",
    ) -> dict[str, object]:
        return {
            "device_code": "private-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://getfloeva.com/authorize",
            "verification_uri_complete": verification_url,
            "expires_in": 600,
            "interval": 5,
        }

    def start_global(self, now: int = 1_000) -> tuple[int, str, str]:
        with mock.patch.object(AUTH, "_request_json", return_value=(200, self.device_response())):
            with mock.patch.object(AUTH.time, "time", return_value=now):
                return self.run_main("start", "global")

    def test_start_stores_secret_without_printing_it(self) -> None:
        result, stdout, stderr = self.start_global()

        self.assertEqual(0, result)
        self.assertEqual("", stderr)
        self.assertIn("https://getfloeva.com/authorize?user_code=ABCD-EFGH", stdout)
        self.assertIn("Confirm code: ABCD-EFGH", stdout)
        self.assertNotIn("private-device-code", stdout)
        session = json.loads(AUTH.SESSION_FILE.read_text(encoding="utf-8"))
        self.assertEqual("private-device-code", session["device_code"])
        self.assertEqual("global", session["region"])
        self.assertEqual(0o600, stat.S_IMODE(AUTH.SESSION_FILE.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(AUTH.CONFIG_DIR.stat().st_mode))

    def test_start_rejects_unexpected_verification_host(self) -> None:
        response = self.device_response(
            "https://attacker.example/authorize?user_code=ABCD-EFGH"
        )
        with mock.patch.object(AUTH, "_request_json", return_value=(200, response)):
            result, stdout, stderr = self.run_main("start", "global")

        self.assertEqual(1, result)
        self.assertEqual("", stdout)
        self.assertIn("unexpected authorization URL", stderr)
        self.assertFalse(AUTH.SESSION_FILE.exists())

    def test_start_accepts_standard_verification_uri_fallback(self) -> None:
        response = self.device_response()
        response.pop("verification_uri_complete")
        response.pop("interval")
        with mock.patch.object(AUTH, "_request_json", return_value=(200, response)):
            result, stdout, stderr = self.run_main("start", "global")

        self.assertEqual(0, result)
        self.assertEqual("", stderr)
        self.assertIn("https://getfloeva.com/authorize", stdout)
        self.assertIn("Confirm code: ABCD-EFGH", stdout)
        session = json.loads(AUTH.SESSION_FILE.read_text(encoding="utf-8"))
        self.assertEqual(5, session["interval"])

    def test_http_redirects_are_not_followed(self) -> None:
        redirect = AUTH.urllib.error.HTTPError(
            "https://us.getfloeva.com/ring/api/open/oauth/device/code",
            302,
            "Found",
            {},
            io.BytesIO(b""),
        )
        opener = mock.Mock()
        opener.open.side_effect = redirect
        with mock.patch.object(AUTH.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(AUTH.CliError, "HTTP 302"):
                AUTH._request_json(
                    "https://us.getfloeva.com/ring/api/open/oauth/device/code",
                    {"client_id": AUTH.CLIENT_ID, "scope": AUTH.SCOPE},
                )

    def test_pending_then_success_preserves_old_config_until_exchange(self) -> None:
        AUTH._atomic_write_json(
            AUTH.CONFIG_FILE,
            {
                "api_key": "legacy-secret",
                "base_url": "https://server.floeva.cn/ring/api",
            },
        )
        old_config = AUTH.CONFIG_FILE.read_bytes()
        self.start_global(now=1_000)

        with mock.patch.object(
            AUTH,
            "_request_json",
            return_value=(400, {"error": "authorization_pending"}),
        ):
            with mock.patch.object(AUTH.time, "time", return_value=1_001):
                result, stdout, stderr = self.run_main("complete")
        self.assertEqual(2, result)
        self.assertEqual("", stdout)
        self.assertIn("still pending", stderr)
        self.assertEqual(old_config, AUTH.CONFIG_FILE.read_bytes())
        self.assertTrue(AUTH.SESSION_FILE.exists())

        request_mock = mock.Mock(
            return_value=(
                200,
                {
                    "access_token": "new-oauth-secret",
                    "token_type": "bearer",
                    "expires_in": 7_776_000,
                },
            )
        )
        with mock.patch.object(AUTH, "_request_json", request_mock):
            with mock.patch.object(AUTH.time, "time", return_value=1_003):
                result, stdout, stderr = self.run_main("complete")
        self.assertEqual(2, result)
        request_mock.assert_not_called()
        self.assertEqual("", stdout)
        self.assertIn("still pending", stderr)

        with mock.patch.object(AUTH, "_request_json", request_mock):
            with mock.patch.object(AUTH.time, "time", return_value=1_006):
                result, stdout, stderr = self.run_main("complete")
        self.assertEqual(0, result)
        self.assertEqual("", stderr)
        self.assertIn("completed", stdout)
        self.assertNotIn("new-oauth-secret", stdout)
        config = json.loads(AUTH.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual("device_authorization", config["auth_mode"])
        self.assertEqual("new-oauth-secret", config["access_token"])
        self.assertEqual("global", config["region"])
        self.assertEqual(0o600, stat.S_IMODE(AUTH.CONFIG_FILE.stat().st_mode))
        self.assertFalse(AUTH.SESSION_FILE.exists())

    def test_slow_down_increases_poll_interval(self) -> None:
        self.start_global(now=1_000)
        with mock.patch.object(
            AUTH, "_request_json", return_value=(400, {"error": "slow_down"})
        ):
            with mock.patch.object(AUTH.time, "time", return_value=1_001):
                result, _, stderr = self.run_main("complete")

        self.assertEqual(2, result)
        self.assertIn("still pending", stderr)
        session = json.loads(AUTH.SESSION_FILE.read_text(encoding="utf-8"))
        self.assertEqual(10, session["interval"])

    def test_access_denied_removes_terminal_session(self) -> None:
        self.start_global(now=1_000)
        with mock.patch.object(
            AUTH, "_request_json", return_value=(401, {"error": "access_denied"})
        ):
            with mock.patch.object(AUTH.time, "time", return_value=1_001):
                result, stdout, stderr = self.run_main("complete")

        self.assertEqual(1, result)
        self.assertEqual("", stdout)
        self.assertIn("access_denied", stderr)
        self.assertFalse(AUTH.SESSION_FILE.exists())

    def test_status_supports_legacy_oauth_expired_and_missing(self) -> None:
        result, stdout, _ = self.run_main("status")
        self.assertEqual((1, "missing\n"), (result, stdout))

        AUTH._atomic_write_json(
            AUTH.CONFIG_FILE,
            {
                "api_key": "legacy-secret",
                "base_url": "https://server.floeva.cn/ring/api",
            },
        )
        result, stdout, _ = self.run_main("status")
        self.assertEqual((0, "legacy\n"), (result, stdout))

        AUTH._atomic_write_json(
            AUTH.CONFIG_FILE,
            {
                "access_token": "oauth-secret",
                "auth_mode": "device_authorization",
                "base_url": "https://us.getfloeva.com/ring/api",
                "expires_at": 2_000,
                "region": "global",
            },
        )
        with mock.patch.object(AUTH.time, "time", return_value=1_900):
            result, stdout, _ = self.run_main("status")
        self.assertEqual((0, "oauth\n"), (result, stdout))
        with mock.patch.object(AUTH.time, "time", return_value=1_940):
            result, stdout, _ = self.run_main("status")
        self.assertEqual((3, "expired\n"), (result, stdout))

    def test_status_rejects_tampered_oauth_region_and_base_url(self) -> None:
        invalid_configs = (
            {
                "access_token": "oauth-secret",
                "auth_mode": "device_authorization",
                "base_url": "http://us.getfloeva.com/ring/api",
                "expires_at": 2_000,
                "region": "global",
            },
            {
                "access_token": "oauth-secret",
                "auth_mode": "device_authorization",
                "base_url": "https://attacker.example/ring/api",
                "expires_at": 2_000,
                "region": "global",
            },
            {
                "access_token": "oauth-secret",
                "auth_mode": "device_authorization",
                "base_url": "https://server.floeva.cn/ring/api",
                "expires_at": 2_000,
                "region": "global",
            },
            {
                "access_token": "oauth-secret",
                "auth_mode": "device_authorization",
                "base_url": "https://us.getfloeva.com/ring/api",
                "expires_at": 2_000,
                "region": "unexpected",
            },
        )
        for config in invalid_configs:
            with self.subTest(config=config):
                AUTH._atomic_write_json(AUTH.CONFIG_FILE, config)
                with mock.patch.object(AUTH.time, "time", return_value=1_000):
                    result, stdout, stderr = self.run_main("status")
                self.assertEqual((3, "expired\n", ""), (result, stdout, stderr))

    def test_corrupt_session_is_removed_with_safe_error(self) -> None:
        AUTH.CONFIG_DIR.mkdir(mode=0o700)
        AUTH.SESSION_FILE.write_text("{not-json", encoding="utf-8")
        os.chmod(AUTH.SESSION_FILE, 0o600)

        result, stdout, stderr = self.run_main("complete")

        self.assertEqual(1, result)
        self.assertEqual("", stdout)
        self.assertIn("invalid. Start again", stderr)
        self.assertFalse(AUTH.SESSION_FILE.exists())

    def test_status_purges_abandoned_expired_session(self) -> None:
        AUTH._atomic_write_json(AUTH.SESSION_FILE, {"expires_at": 900})
        with mock.patch.object(AUTH.time, "time", return_value=1_000):
            result, stdout, _ = self.run_main("status")

        self.assertEqual((1, "missing\n"), (result, stdout))
        self.assertFalse(AUTH.SESSION_FILE.exists())


class InstallerTest(unittest.TestCase):
    def test_local_install_copies_complete_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / ".codex").mkdir()
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            result = subprocess.run(
                ["/bin/sh", str(ROOT / "install.sh")],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            target = home / ".codex" / "skills" / "floeva-smart-ring"
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertTrue((target / "agents" / "openai.yaml").is_file())
            self.assertTrue((target / "scripts" / "floeva-auth.sh").is_file())
            self.assertTrue((target / "scripts" / "floeva-auth.py").is_file())
            self.assertTrue(os.access(target / "scripts" / "floeva-auth.sh", os.X_OK))
            self.assertTrue(os.access(target / "scripts" / "floeva-auth.py", os.X_OK))

    def test_install_failure_keeps_existing_skill_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            target = home / ".codex" / "skills" / "floeva-smart-ring"
            target.mkdir(parents=True)
            old_skill = "old working skill\n"
            (target / "SKILL.md").write_text(old_skill, encoding="utf-8")

            fake_bin = home / "fake-bin"
            fake_bin.mkdir()
            fake_cp = fake_bin / "cp"
            fake_cp.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in */SKILL.md) exit 9 ;; esac\n"
                "exec /bin/cp \"$@\"\n",
                encoding="utf-8",
            )
            os.chmod(fake_cp, 0o755)

            environment = os.environ.copy()
            environment["HOME"] = str(home)
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            result = subprocess.run(
                ["/bin/sh", str(ROOT / "install.sh")],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(old_skill, (target / "SKILL.md").read_text(encoding="utf-8"))
            self.assertTrue((target / "scripts" / "floeva-auth.py").is_file())
            self.assertTrue((target / "scripts" / "floeva-auth.sh").is_file())
            self.assertFalse(list(target.rglob(".floeva-install.*")))

    def test_docs_no_longer_request_api_key_paste(self) -> None:
        for path in (ROOT / "SKILL.md", ROOT / "README.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Please paste your API Key", text)
            self.assertNotIn("Floeva API Key Required", text)


if __name__ == "__main__":
    unittest.main()
