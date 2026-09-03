#!/usr/bin/env python3
"""Deterministic WorkBuddy package builder tests."""

from __future__ import annotations

import hashlib
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
    def fixture_source(self, root: Path, with_gate: bool = True) -> Path:
        source = root / "source"
        source.mkdir()
        for name in ("connector-meta.json", "icon.svg", "skill-overlay.md"):
            (source / name).write_bytes((ROOT / "workbuddy" / "cn" / name).read_bytes())
        mcp = {
            "preAuth": "cli",
            "mcpServers": {
                "floeva-health-cn": {
                    "type": "stdio",
                    "command": "node",
                    "args": ["runtime/server.mjs"],
                    "timeout": 30000,
                    "runtime": {"type": "node", "version": "20"},
                }
            },
        }
        command = "python scripts/floeva-auth.py {action} --client floeva-workbuddy-cn"
        cli = {
            "runtime": {"type": "python", "version": "3.11"},
            "init": {platform: command.format(action="init") for platform in BUILDER.PLATFORMS},
            "auth": {platform: command.format(action="start --region cn") for platform in BUILDER.PLATFORMS},
            "status": {platform: command.format(action="status") for platform in BUILDER.PLATFORMS},
            "unAuth": {platform: command.format(action="logout") for platform in BUILDER.PLATFORMS},
            "statusMatch": "^oauth$",
            "authUrlDomain": "floeva.cn",
            "authDeviceFlow": {"fixture": "schema supplied by WorkBuddy gate"},
        }
        self.write_json(source / "mcp.json", mcp)
        self.write_json(source / "cli.json", cli)
        if with_gate:
            self.write_json(
                source / "gate-approval.json",
                {
                    "schema_reference": "test-fixture://wb-1",
                    "runtime_reference": "test-fixture://wb-2",
                    "verified_at": "2026-09-03",
                    "mcp_sha256": self.digest(source / "mcp.json"),
                    "cli_sha256": self.digest(source / "cli.json"),
                },
            )
        return source

    def test_build_is_byte_deterministic_and_contains_only_review_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture_source(root)
            bundle = root / "server.mjs"
            bundle.write_text("console.error('stdio');\n", encoding="utf-8")
            first = root / "first.zip"
            second = root / "second.zip"

            digest_a = BUILDER.build_connector(first, source, bundle, run_mcp_build=False)
            digest_b = BUILDER.build_connector(second, source, bundle, run_mcp_build=False)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(digest_a, digest_b)
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(sorted(archive.namelist()), archive.namelist())
                self.assertFalse(any(".DS_Store" in name for name in archive.namelist()))
                skill = archive.read("skills/floeva-smart-ring/SKILL.md").decode("utf-8")
                self.assertNotIn("Authorization:", skill)
                self.assertNotIn("/open/v1", skill)

    def test_release_build_stops_at_exact_external_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture_source(root, with_gate=False)
            bundle = root / "server.mjs"
            bundle.write_text("export {};\n", encoding="utf-8")

            with self.assertRaisesRegex(BUILDER.PackageError, "BLOCKED WB-1/WB-2"):
                BUILDER.build_connector(root / "blocked.zip", source, bundle, run_mcp_build=False)
            self.assertFalse((root / "blocked.zip").exists())

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
