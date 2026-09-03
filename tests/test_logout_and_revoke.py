#!/usr/bin/env python3
"""WorkBuddy unAuth and self-revoke behavior tests."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "floeva_auth_logout", ROOT / "scripts" / "floeva-auth.py"
)
assert SPEC and SPEC.loader
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class LogoutAndRevokeTest(unittest.TestCase):
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

    def write_authorization(self) -> None:
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
        AUTH._atomic_write_json(
            self.paths["session"],
            {
                "client_id": "floeva-workbuddy-cn",
                "client_instance_id": self.INSTANCE_ID,
                "expires_at": 2_000,
            },
        )

    def test_logout_revokes_then_removes_credential_and_session_but_keeps_identity(self) -> None:
        self.write_authorization()
        request = mock.Mock(return_value=(200, {"revoked": True}))

        with mock.patch.object(AUTH, "_request_json", request):
            result = self.run_main("logout", "--client", "floeva-workbuddy-cn")

        self.assertEqual((0, "logged_out\n", ""), result)
        self.assertFalse(self.paths["credential"].exists())
        self.assertFalse(self.paths["session"].exists())
        self.assertTrue(self.paths["instance"].exists())
        url, payload = request.call_args.args[:2]
        headers = request.call_args.kwargs["headers"]
        self.assertEqual("https://server.floeva.cn/ring/api/open/oauth/revoke", url)
        self.assertEqual({}, payload)
        self.assertEqual(f"Bearer {self.TOKEN}", headers["Authorization"])
        self.assertNotIn(self.TOKEN, result[1] + result[2])
        self.assertNotIn(self.INSTANCE_ID, result[1] + result[2])

    def test_logout_network_failure_keeps_local_state_for_retry(self) -> None:
        self.write_authorization()
        with mock.patch.object(AUTH, "_request_json", side_effect=AUTH.CliError("network failed")):
            result = self.run_main("logout", "--client", "floeva-workbuddy-cn")

        self.assertEqual(1, result[0])
        self.assertIn("network failed", result[2])
        self.assertTrue(self.paths["credential"].exists())
        self.assertTrue(self.paths["session"].exists())
        self.assertTrue(self.paths["instance"].exists())

    def test_repeated_logout_is_successful_and_does_not_call_network(self) -> None:
        request = mock.Mock()
        with mock.patch.object(AUTH, "_request_json", request):
            first = self.run_main("logout", "--client", "floeva-workbuddy-cn")
            second = self.run_main("logout", "--client", "floeva-workbuddy-cn")

        self.assertEqual((0, "logged_out\n", ""), first)
        self.assertEqual(first, second)
        request.assert_not_called()
        self.assertTrue(self.paths["instance"].exists())

    def test_explicit_local_cleanup_never_claims_remote_revoke(self) -> None:
        self.write_authorization()
        result = self.run_main("cleanup-local", "--client", "floeva-workbuddy-cn")

        self.assertEqual((0, "local_state_removed\n", ""), result)
        self.assertFalse(self.paths["credential"].exists())
        self.assertFalse(self.paths["session"].exists())
        self.assertTrue(self.paths["instance"].exists())

    def test_local_cleanup_reports_tombstone_deletion_failure(self) -> None:
        self.write_authorization()
        real_unlink = Path.unlink

        def fail_tombstone_unlink(path: Path, *args: object, **kwargs: object) -> None:
            if ".remove-" in path.name:
                raise OSError("simulated deletion failure")
            real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_tombstone_unlink):
            result = self.run_main("cleanup-local", "--client", "floeva-workbuddy-cn")

        self.assertEqual(1, result[0])
        self.assertIn("Unable to remove local Floeva authorization state completely.", result[2])
        self.assertNotIn(self.TOKEN, result[1] + result[2])
        self.assertNotIn(self.INSTANCE_ID, result[1] + result[2])


if __name__ == "__main__":
    unittest.main()
