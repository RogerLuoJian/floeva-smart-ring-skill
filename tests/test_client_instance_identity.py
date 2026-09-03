#!/usr/bin/env python3
"""Independent WorkBuddy installation identity tests."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "floeva_auth_instances", ROOT / "scripts" / "floeva-auth.py"
)
assert SPEC and SPEC.loader
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class ClientInstanceIdentityTest(unittest.TestCase):
    def run_main(self, home: Path, *args: str) -> tuple[int, str, str]:
        AUTH.HOME_DIR = home
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = AUTH.main(["floeva-auth.py", *args])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_a_and_b_are_distinct_and_reinitializing_a_does_not_touch_b(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home_a = root / "a"
            home_b = root / "b"
            ids = [
                uuid.UUID("01234567-89ab-4def-8123-456789abcdef"),
                uuid.UUID("fedcba98-7654-4abc-9123-456789abcdef"),
            ]
            with mock.patch.object(AUTH.uuid, "uuid4", side_effect=ids):
                self.assertEqual(0, self.run_main(home_a, "init", "--client", "floeva-workbuddy-cn")[0])
                self.assertEqual(0, self.run_main(home_b, "init", "--client", "floeva-workbuddy-cn")[0])

            profile = AUTH._require_client_profile("floeva-workbuddy-cn")
            AUTH.HOME_DIR = home_a
            instance_a = AUTH._load_json(AUTH._client_paths(profile)["instance"])
            AUTH.HOME_DIR = home_b
            paths_b = AUTH._client_paths(profile)
            instance_b = AUTH._load_json(paths_b["instance"])
            b_before = paths_b["instance"].read_bytes()

            self.assertNotEqual(instance_a["client_instance_id"], instance_b["client_instance_id"])
            with mock.patch.object(AUTH.uuid, "uuid4") as random_uuid:
                self.assertEqual(0, self.run_main(home_a, "init", "--client", "floeva-workbuddy-cn")[0])
            random_uuid.assert_not_called()
            self.assertEqual(b_before, paths_b["instance"].read_bytes())


if __name__ == "__main__":
    unittest.main()
