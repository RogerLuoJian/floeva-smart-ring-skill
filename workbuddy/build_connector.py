#!/usr/bin/env python3
"""Build and validate a deterministic WorkBuddy connector review archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "workbuddy" / "cn"
MCP_ROOT = REPO_ROOT / "mcp"
MCP_BUNDLE = MCP_ROOT / "build" / "server.mjs"
PLATFORMS = {"darwin", "linux", "win32"}
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SOURCE = "floeva-health-cn"
TOKEN_PATTERN = re.compile(rb"fv_sk_[A-Za-z0-9]{32}")


class PackageError(Exception):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackageError(f"Invalid or missing JSON file: {path.name}") from exc
    if not isinstance(value, dict):
        raise PackageError(f"JSON root must be an object: {path.name}")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_gate(source_root: Path) -> tuple[Path, Path]:
    mcp_path = source_root / "mcp.json"
    cli_path = source_root / "cli.json"
    gate_path = source_root / "gate-approval.json"
    if not mcp_path.is_file() or not cli_path.is_file():
        raise PackageError(
            "BLOCKED WB-1/WB-2: approved cli.json Device Flow schema and packaged-runtime path rules are unavailable."
        )
    if not gate_path.is_file():
        raise PackageError(
            "BLOCKED WB-1/WB-2: gate-approval.json must bind the exact reviewed mcp.json and cli.json."
        )
    gate = _load_object(gate_path)
    required_strings = ("schema_reference", "runtime_reference", "verified_at")
    if any(not isinstance(gate.get(name), str) or not gate[name] for name in required_strings):
        raise PackageError("WB-1/WB-2 gate evidence is incomplete.")
    if gate.get("mcp_sha256") != _digest(mcp_path) or gate.get("cli_sha256") != _digest(cli_path):
        raise PackageError("WB-1/WB-2 gate evidence does not match the current configs.")
    return mcp_path, cli_path


def _validate_configs(source_root: Path) -> tuple[Path, Path]:
    mcp_path, cli_path = _validate_gate(source_root)
    metadata = _load_object(source_root / "connector-meta.json")
    if (
        metadata.get("source") != SOURCE
        or metadata.get("type") != "mcp"
        or metadata.get("minWorkbuddyVersion") != "5.0.0"
    ):
        raise PackageError("Connector metadata contract is invalid.")
    for field in ("name", "name_en", "description", "description_zh", "description_en", "version"):
        if not isinstance(metadata.get(field), str) or not metadata[field]:
            raise PackageError(f"Connector metadata field is missing: {field}")
    for field in ("examples_zh", "examples_en"):
        value = metadata.get(field)
        if not isinstance(value, list) or not 2 <= len(value) <= 5 or not all(isinstance(item, str) and item for item in value):
            raise PackageError(f"Connector metadata examples are invalid: {field}")

    mcp = _load_object(mcp_path)
    servers = mcp.get("mcpServers")
    if mcp.get("preAuth") != "cli" or not isinstance(servers, dict) or len(servers) != 1:
        raise PackageError("mcp.json must contain one pre-authenticated MCP server.")
    server = next(iter(servers.values()))
    if not isinstance(server, dict):
        raise PackageError("mcp.json server entry is invalid.")
    runtime = server.get("runtime")
    if (
        server.get("type") != "stdio"
        or server.get("command") != "node"
        or server.get("timeout") != 30000
        or runtime != {"type": "node", "version": "20"}
        or "headers" in server
        or "env" in server
        or "staticHeaders" in server
        or "staticEnv" in server
    ):
        raise PackageError("mcp.json violates the local Node 20 stdio contract.")
    args = server.get("args")
    if not isinstance(args, list) or len(args) != 1 or not _safe_relative_path(args[0], ".mjs"):
        raise PackageError("mcp.json must launch one packaged relative .mjs entrypoint.")

    cli = _load_object(cli_path)
    runtime = cli.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("type") != "python":
        raise PackageError("cli.json must declare the WorkBuddy Python runtime.")
    if cli.get("authUrlDomain") != "floeva.cn" or "authDeviceFlow" not in cli:
        raise PackageError("cli.json is missing the approved Floeva Device Flow contract.")
    if cli.get("statusMatch") != "^oauth$":
        raise PackageError("cli.json statusMatch must match only the stable oauth state.")
    for action in ("init", "auth", "status", "unAuth"):
        commands = cli.get(action)
        if not isinstance(commands, dict) or set(commands) != PLATFORMS:
            raise PackageError(f"cli.json {action} commands must cover darwin/linux/win32.")
        for command in commands.values():
            if not isinstance(command, str) or "floeva-auth.py" not in command or "floeva-workbuddy-cn" not in command:
                raise PackageError(f"cli.json {action} command is not bound to the Floeva WorkBuddy client.")
    return mcp_path, cli_path


def _safe_relative_path(value: Any, suffix: str) -> bool:
    if not isinstance(value, str) or not value.endswith(suffix) or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and len(path.parts) > 1


def _source_entries(
    source_root: Path, mcp_path: Path, cli_path: Path, bundle_path: Path
) -> list[tuple[str, Path, int]]:
    entries = [
        ("connector-meta.json", source_root / "connector-meta.json", 0o644),
        ("mcp.json", mcp_path, 0o644),
        ("cli.json", cli_path, 0o644),
        ("icon.svg", source_root / "icon.svg", 0o644),
        ("runtime/server.mjs", bundle_path, 0o644),
        ("scripts/floeva-auth.py", REPO_ROOT / "scripts" / "floeva-auth.py", 0o755),
        ("skills/floeva-smart-ring/SKILL.md", source_root / "skill-overlay.md", 0o644),
        (
            "skills/floeva-smart-ring/references/data-presentation.md",
            REPO_ROOT / "references" / "data-presentation.md",
            0o644,
        ),
    ]
    for archive_name, path, _ in entries:
        if path.is_symlink() or not path.is_file():
            raise PackageError(f"Required package file is missing or a symlink: {archive_name}")
    return sorted(entries, key=lambda item: item[0])


def _scan_entry(name: str, content: bytes) -> None:
    if name.endswith(".DS_Store") or name.startswith("/") or ".." in Path(name).parts:
        raise PackageError(f"Unsafe package path: {name}")
    if TOKEN_PATTERN.search(content) or b"-----BEGIN PRIVATE KEY-----" in content:
        raise PackageError(f"Potential secret in package entry: {name}")


def build_connector(
    output: Path,
    source_root: Path = SOURCE_ROOT,
    bundle_path: Path = MCP_BUNDLE,
    run_mcp_build: bool = True,
) -> str:
    mcp_path, cli_path = _validate_configs(source_root)
    if run_mcp_build:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=MCP_ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise PackageError("MCP build failed; run npm ci and npm run build.")
    entries = _source_entries(source_root, mcp_path, cli_path, bundle_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, path, mode in entries:
                content = path.read_bytes()
                _scan_entry(name, content)
                info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | mode) << 16
                archive.writestr(info, content)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    validate_archive(output)
    return _digest(output)


def validate_archive(path: Path) -> None:
    expected = {
        "connector-meta.json",
        "mcp.json",
        "cli.json",
        "icon.svg",
        "runtime/server.mjs",
        "scripts/floeva-auth.py",
        "skills/floeva-smart-ring/SKILL.md",
        "skills/floeva-smart-ring/references/data-presentation.md",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if set(names) != expected or names != sorted(names):
                raise PackageError("Connector archive entries are incomplete or non-deterministic.")
            for info in archive.infolist():
                if info.is_dir() or info.date_time != ZIP_TIMESTAMP:
                    raise PackageError("Connector archive metadata is non-deterministic.")
                _scan_entry(info.filename, archive.read(info))
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackageError("Connector archive is unreadable.") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "workbuddy" / "dist" / f"{SOURCE}-0.1.0.zip",
    )
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.validate:
            validate_archive(args.validate)
            print("valid")
        else:
            digest = build_connector(args.output)
            print(f"built {args.output.name} sha256={digest}")
        return 0
    except PackageError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
