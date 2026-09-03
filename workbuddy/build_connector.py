#!/usr/bin/env python3
"""Build and validate a deterministic WorkBuddy connector review archive."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "workbuddy" / "cn"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SOURCE = "floeva-health-cn"
VERSION = "0.2.1"
MAX_ARCHIVE_ENTRY_BYTES = 1024 * 1024
TOKEN_PATTERN = re.compile(rb"fv_sk_[A-Za-z0-9]{32}")
EXPECTED_CLI_CONFIG = {
    "runtime": {"type": "python", "version": "3.11"},
    "init": {
        "darwin": "python3 scripts/floeva-auth.py init --client floeva-workbuddy-cn",
        "linux": "python3 scripts/floeva-auth.py init --client floeva-workbuddy-cn",
        "win32": "python scripts/floeva-auth.py init --client floeva-workbuddy-cn",
    },
    "auth": {
        "darwin": "python3 scripts/floeva-auth.py auth --client floeva-workbuddy-cn --region cn",
        "linux": "python3 scripts/floeva-auth.py auth --client floeva-workbuddy-cn --region cn",
        "win32": "python scripts/floeva-auth.py auth --client floeva-workbuddy-cn --region cn",
    },
    "unAuth": {
        "darwin": "python3 scripts/floeva-auth.py logout --client floeva-workbuddy-cn",
        "linux": "python3 scripts/floeva-auth.py logout --client floeva-workbuddy-cn",
        "win32": "python scripts/floeva-auth.py logout --client floeva-workbuddy-cn",
    },
    "status": {
        "darwin": "python3 scripts/floeva-auth.py status --client floeva-workbuddy-cn",
        "linux": "python3 scripts/floeva-auth.py status --client floeva-workbuddy-cn",
        "win32": "python scripts/floeva-auth.py status --client floeva-workbuddy-cn",
    },
    "statusMatch": "^oauth$",
    "authUrlDomain": "floeva.cn",
}
EXPECTED_MODES = {
    "connector-meta.json": 0o644,
    "cli.json": 0o644,
    "icon.svg": 0o644,
    "scripts/floeva-auth.py": 0o755,
    "skills/floeva-smart-ring/SKILL.md": 0o644,
    "skills/floeva-smart-ring/references/data-presentation.md": 0o644,
    "skills/floeva-smart-ring/scripts/floeva-auth.py": 0o755,
}


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


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PackageError(f"Invalid or missing text file: {path.name}") from exc


def _validate_contract(
    metadata: dict[str, Any], cli: dict[str, Any], skill_text: str
) -> None:
    if (
        metadata.get("source") != SOURCE
        or metadata.get("type") != "cli"
        or metadata.get("version") != VERSION
        or metadata.get("minWorkbuddyVersion") != "5.0.0"
    ):
        raise PackageError("Connector metadata contract is invalid.")
    for field in (
        "name",
        "name_en",
        "description",
        "description_zh",
        "description_en",
        "version",
    ):
        if not isinstance(metadata.get(field), str) or not metadata[field]:
            raise PackageError(f"Connector metadata field is missing: {field}")
    for field in ("examples_zh", "examples_en"):
        value = metadata.get(field)
        if (
            not isinstance(value, list)
            or not 2 <= len(value) <= 5
            or not all(isinstance(item, str) and item for item in value)
        ):
            raise PackageError(f"Connector metadata examples are invalid: {field}")

    if cli != EXPECTED_CLI_CONFIG:
        raise PackageError("cli.json does not match the reviewed Python CLI contract.")
    lines = skill_text.splitlines()
    if len(lines) < 3 or lines[0] != "---" or "---" not in lines[1:]:
        raise PackageError("WorkBuddy Skill frontmatter is invalid.")
    end = lines[1:].index("---") + 1
    frontmatter: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise PackageError("WorkBuddy Skill frontmatter is invalid.")
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    required = {
        "name",
        "display_name",
        "display_name_en",
        "description",
        "description_zh",
        "description_en",
        "allowed-tools",
        "version",
        "author",
    }
    if set(frontmatter) != required or any(not frontmatter[key] for key in required):
        raise PackageError("WorkBuddy Skill frontmatter fields are incomplete.")
    if (
        frontmatter["name"] != "floeva-smart-ring"
        or frontmatter["allowed-tools"] != "Bash"
        or frontmatter["version"] != VERSION
        or frontmatter["author"] != "Floeva"
    ):
        raise PackageError("WorkBuddy Skill frontmatter contract is invalid.")
    forbidden = (
        "authorization:",
        "/open/v1",
        "access_token=$(",
        "config.json",
        "curl ",
        "mcp",
    )
    lowered = skill_text.lower()
    if any(value in lowered for value in forbidden):
        raise PackageError("WorkBuddy Skill bypasses the reviewed CLI boundary.")
    for command in (" overview ", " tools ", " call "):
        if command not in skill_text:
            raise PackageError("WorkBuddy Skill is missing a required CLI query command.")


def _validate_configs(source_root: Path) -> Path:
    cli_path = source_root / "cli.json"
    _validate_contract(
        _load_object(source_root / "connector-meta.json"),
        _load_object(cli_path),
        _load_text(source_root / "skill-overlay.md"),
    )
    return cli_path


def _source_entries(source_root: Path, cli_path: Path) -> list[tuple[str, Path, int]]:
    auth_script = REPO_ROOT / "scripts" / "floeva-auth.py"
    entries = [
        ("connector-meta.json", source_root / "connector-meta.json", 0o644),
        ("cli.json", cli_path, 0o644),
        ("icon.svg", source_root / "icon.svg", 0o644),
        ("scripts/floeva-auth.py", auth_script, 0o755),
        ("skills/floeva-smart-ring/SKILL.md", source_root / "skill-overlay.md", 0o644),
        ("skills/floeva-smart-ring/scripts/floeva-auth.py", auth_script, 0o755),
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
) -> None:
    cli_path = _validate_configs(source_root)
    entries = _source_entries(source_root, cli_path)
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


def validate_archive(path: Path) -> None:
    expected = set(EXPECTED_MODES)
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(expected) or set(names) != expected or names != sorted(names):
                raise PackageError("Connector archive entries are incomplete or non-deterministic.")
            for info in archive.infolist():
                mode = info.external_attr >> 16
                if (
                    info.is_dir()
                    or info.date_time != ZIP_TIMESTAMP
                    or not stat.S_ISREG(mode)
                    or stat.S_IMODE(mode) != EXPECTED_MODES[info.filename]
                    or info.file_size > MAX_ARCHIVE_ENTRY_BYTES
                ):
                    raise PackageError("Connector archive metadata is non-deterministic.")
                _scan_entry(info.filename, archive.read(info))
            root_script = archive.read("scripts/floeva-auth.py")
            skill_script = archive.read("skills/floeva-smart-ring/scripts/floeva-auth.py")
            if root_script != skill_script:
                raise PackageError("Packaged CLI script copies do not match.")
            try:
                metadata = json.loads(archive.read("connector-meta.json").decode("utf-8"))
                cli = json.loads(archive.read("cli.json").decode("utf-8"))
                skill_text = archive.read("skills/floeva-smart-ring/SKILL.md").decode("utf-8")
            except (UnicodeDecodeError, ValueError) as exc:
                raise PackageError("Connector archive configuration is unreadable.") from exc
            if not isinstance(metadata, dict) or not isinstance(cli, dict):
                raise PackageError("Connector archive configuration is invalid.")
            _validate_contract(metadata, cli, skill_text)
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackageError("Connector archive is unreadable.") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "workbuddy" / "dist" / f"{SOURCE}-{VERSION}.zip",
    )
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.validate:
            validate_archive(args.validate)
            print("valid")
        else:
            build_connector(args.output)
            print(f"built {args.output.name}")
        return 0
    except PackageError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
