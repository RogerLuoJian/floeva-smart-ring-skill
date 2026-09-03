#!/usr/bin/env python3
"""Deterministic WorkBuddy package builder tests."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "workbuddy_builder", ROOT / "workbuddy" / "build_connector.py"
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class WorkBuddyPackageTest(unittest.TestCase):
    def fixture_source(self, root: Path) -> Path:
        source = root / "source"
        source.mkdir()
        for name in ("connector-meta.json", "icon.svg", "skill-overlay.md", "cli.json"):
            (source / name).write_bytes((ROOT / "workbuddy" / "cn" / name).read_bytes())
        return source

    def test_build_is_byte_deterministic_and_contains_only_review_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture_source(root)
            first = root / "first.zip"
            second = root / "second.zip"

            BUILDER.build_connector(first, source)
            BUILDER.build_connector(second, source)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(sorted(archive.namelist()), archive.namelist())
                self.assertFalse(any(".DS_Store" in name for name in archive.namelist()))
                self.assertNotIn("mcp.json", archive.namelist())
                skill = archive.read("skills/floeva-smart-ring/SKILL.md").decode("utf-8")
                self.assertNotIn("Authorization:", skill)
                self.assertNotIn("/open/v1", skill)
                self.assertIn("allowed-tools: Bash", skill)
                self.assertEqual(
                    archive.read("scripts/floeva-auth.py"),
                    archive.read("skills/floeva-smart-ring/scripts/floeva-auth.py"),
                )

    def test_config_uses_documented_cli_skill_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture_source(root)
            cli = json.loads((source / "cli.json").read_text(encoding="utf-8"))

            self.assertEqual({"type": "python", "version": "3.11"}, cli["runtime"])
            self.assertEqual("floeva.cn", cli["authUrlDomain"])
            self.assertEqual("^oauth$", cli["statusMatch"])
            self.assertEqual({"darwin", "linux", "win32"}, set(cli["auth"]))
            self.assertTrue(all(" auth " in command for command in cli["auth"].values()))
            BUILDER.build_connector(root / "connector.zip", source)

    def test_builder_rejects_skill_that_bypasses_cli_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture_source(root)
            skill_path = source / "skill-overlay.md"
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8") + "\nUse an MCP fallback.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(BUILDER.PackageError, "CLI boundary"):
                BUILDER.build_connector(root / "connector.zip", source)

if __name__ == "__main__":
    unittest.main()
