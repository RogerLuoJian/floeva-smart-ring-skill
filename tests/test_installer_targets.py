#!/usr/bin/env python3
"""Contract tests for explicit and legacy skill installation targets."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
RUNTIME_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/floeva-auth.sh",
    "scripts/floeva-auth.py",
    "scripts/floeva-report.py",
    "references/data-presentation.md",
    "references/health-canvas.md",
    "assets/health-report/index.html",
    "assets/health-report/app.css",
    "assets/health-report/app.js",
    "assets/health-report/logo-icon.svg",
    "assets/health-report/lotus.svg",
    "assets/health-report/fonts/Inter-Regular.ttf",
    "assets/health-report/fonts/Inter-Bold.ttf",
)
LEGACY_AGENTS = (".codex", ".claude", ".openclaw")


class InstallerTargetsTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {**os.environ, "HOME": str(self.home)}

    def run_installer(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(INSTALLER), *args], cwd=self.root, env=self.env,
            text=True, capture_output=True, check=False,
        )

    def assert_runtime(self, target: Path) -> None:
        for relative in RUNTIME_FILES:
            with self.subTest(file=relative, target=target):
                self.assertEqual((ROOT / relative).read_bytes(), (target / relative).read_bytes())

    def snapshot(self) -> dict[str, bytes | None]:
        return {
            str(path.relative_to(self.root)): path.read_bytes() if path.is_file() else None
            for path in self.root.rglob("*")
        }

    def test_explicit_absolute_target_with_spaces_is_exclusive_and_usable(self) -> None:
        for agent in LEGACY_AGENTS:
            (self.home / agent).mkdir()
        target = self.root / "Future Agent" / "skills" / "floeva-smart-ring"
        result = self.run_installer("--target", str(target))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_runtime(target)
        for agent in LEGACY_AGENTS:
            self.assertFalse((self.home / agent / "skills").exists())
        status = subprocess.run(
            [str(target / "scripts/floeva-auth.sh"), "status", "--agent-name", "Future Agent"],
            env=self.env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(1, status.returncode, status.stderr)
        self.assertEqual("missing", status.stdout.strip())

    def test_relative_target_resolves_from_working_directory(self) -> None:
        target = Path("another agent/skills/floeva-smart-ring")
        result = self.run_installer("--target", str(target))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_runtime(self.root / target)
        for agent in (*LEGACY_AGENTS, ".agents"):
            self.assertFalse((self.home / agent).exists())

    def test_help_succeeds_without_writes(self) -> None:
        (self.home / ".codex").mkdir()
        before = self.snapshot()
        result = self.run_installer("--help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_invalid_arguments_are_rejected_before_writes(self) -> None:
        (self.home / ".codex").mkdir()
        target = str(self.root / "target")
        for args in (("--target",), ("--unknown",), ("--target", target, "--unknown"),
                     ("--target", target, "--target", str(self.root / "other")),
                     ("--target", "")):
            with self.subTest(args=args):
                before = self.snapshot()
                result = self.run_installer(*args)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertEqual(before, self.snapshot())

    def test_no_arguments_install_to_all_existing_legacy_agents(self) -> None:
        for agent in LEGACY_AGENTS:
            (self.home / agent).mkdir()
        result = self.run_installer()
        self.assertEqual(0, result.returncode, result.stderr)
        for agent in LEGACY_AGENTS:
            self.assert_runtime(self.home / agent / "skills/floeva-smart-ring")
        self.assertFalse((self.home / ".agents").exists())

    def test_no_arguments_fall_back_to_agents_when_no_legacy_agent_exists(self) -> None:
        result = self.run_installer()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_runtime(self.home / ".agents/skills/floeva-smart-ring")


if __name__ == "__main__":
    unittest.main()
