#!/usr/bin/env python3
"""Secure OAuth device authorization helper for Floeva clients."""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


LEGACY_CLIENT_ID = "floeva-smart-ring-skill"
WORKBUDDY_CN_CLIENT_ID = "floeva-workbuddy-cn"
# Backward-compatible public constant used by existing tests and callers.
CLIENT_ID = LEGACY_CLIENT_ID
SCOPE = "health:read"
USER_AGENT = "Floeva-Smart-Ring-Skill/1.0"
EXPIRY_SKEW_SECONDS = 60
CLIENT_INSTANCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
REGIONS = {
    "global": {
        "base_url": "https://us.getfloeva.com/ring/api",
        "verification_host": "getfloeva.com",
    },
    "cn": {
        "base_url": "https://server.floeva.cn/ring/api",
        "verification_host": "floeva.cn",
    },
}
CLIENT_PROFILES: dict[str, dict[str, Any]] = {
    LEGACY_CLIENT_ID: {
        "client_id": LEGACY_CLIENT_ID,
        "regions": ("global", "cn"),
        "base_urls": {name: value["base_url"] for name, value in REGIONS.items()},
        "verification_hosts": {
            name: value["verification_host"] for name, value in REGIONS.items()
        },
        "requires_instance": False,
        "dedicated_store": False,
    },
    WORKBUDDY_CN_CLIENT_ID: {
        "client_id": WORKBUDDY_CN_CLIENT_ID,
        "regions": ("cn",),
        "base_urls": {"cn": REGIONS["cn"]["base_url"]},
        "verification_hosts": {"cn": REGIONS["cn"]["verification_host"]},
        "requires_instance": True,
        "dedicated_store": True,
    },
}
HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".floeva"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSION_FILE = CONFIG_DIR / "device-authorization.json"


class CliError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Any,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            os.chmod(temp_path, 0o600)
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _atomic_remove_files(paths: list[Path]) -> None:
    """Make a group of local state files disappear together, with rollback on error."""
    existing = [path for path in paths if path.is_file()]
    moved: list[tuple[Path, Path]] = []
    try:
        for path in existing:
            tombstone = path.with_name(f".{path.name}.remove-{secrets.token_hex(8)}")
            os.replace(path, tombstone)
            moved.append((path, tombstone))
    except OSError as exc:
        for original, tombstone in reversed(moved):
            if tombstone.exists():
                os.replace(tombstone, original)
        raise CliError("Unable to update local Floeva authorization state.") from exc
    cleanup_failed = False
    for _, tombstone in moved:
        try:
            tombstone.unlink()
        except OSError:
            cleanup_failed = True
    if cleanup_failed:
        raise CliError("Unable to remove local Floeva authorization state completely.")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError) as exc:
        raise CliError(f"Floeva authorization state is unreadable: {path.name}.") from exc
    if not isinstance(payload, dict):
        raise CliError(f"Floeva authorization state is invalid: {path.name}.")
    return payload


def _require_private_file(path: Path) -> None:
    if os.name != "nt" and path.is_file() and path.stat().st_mode & 0o077:
        raise CliError("Floeva authorization state permissions are unsafe.")


def _request_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()
    except urllib.error.URLError as exc:
        raise CliError("Unable to reach the Floeva authorization service.") from exc

    if status not in {200, 400, 401}:
        raise CliError(f"Floeva authorization service returned HTTP {status}.")
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CliError("Floeva returned an unreadable authorization response.") from exc
    if not isinstance(decoded, dict):
        raise CliError("Floeva returned an invalid authorization response.")
    return status, decoded


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise CliError(f"Floeva returned an invalid {field} value.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CliError(f"Floeva returned an invalid {field} value.") from exc
    if parsed <= 0:
        raise CliError(f"Floeva returned an invalid {field} value.")
    return parsed


def _require_client_profile(client_id: str) -> dict[str, Any]:
    profile = CLIENT_PROFILES.get(client_id)
    if profile is None:
        raise CliError("Unknown Floeva client.")
    return profile


def _client_paths(profile: dict[str, Any]) -> dict[str, Path | None]:
    if not profile["dedicated_store"]:
        return {
            "root": CONFIG_DIR,
            "instance": None,
            "credential": CONFIG_FILE,
            "session": SESSION_FILE,
        }
    root = HOME_DIR / ".floeva" / "workbuddy" / profile["client_id"]
    return {
        "root": root,
        "instance": root / "instance.json",
        "credential": root / "credential.json",
        "session": root / "device-authorization.json",
    }


def _validate_verification_url(
    url: str,
    region: str,
    user_code: str | None = None,
    profile: dict[str, Any] | None = None,
) -> None:
    selected = profile or _require_client_profile(LEGACY_CLIENT_ID)
    parsed = urlparse(url)
    expected_host = selected["verification_hosts"].get(region)
    query_code = parse_qs(parsed.query).get("user_code", [""])[0]
    query_is_valid = (
        not parsed.query
        if user_code is None
        else query_code.replace("-", "").upper() == user_code.replace("-", "").upper()
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path.rstrip("/") != "/authorize"
        or not query_is_valid
    ):
        raise CliError("Floeva returned an unexpected authorization URL.")


def _purge_expired_session(path: Path | None = None) -> None:
    session_path = path or SESSION_FILE
    if not session_path.is_file():
        return
    try:
        session = _load_json(session_path)
        expires_at = int(session.get("expires_at"))
    except (CliError, TypeError, ValueError):
        session_path.unlink(missing_ok=True)
        return
    if int(time.time()) >= expires_at:
        session_path.unlink(missing_ok=True)


def _ensure_installation_identity(profile: dict[str, Any]) -> dict[str, Any]:
    if not profile["requires_instance"]:
        raise CliError("This Floeva client does not use an installation identity.")
    path = _client_paths(profile)["instance"]
    assert isinstance(path, Path)
    if path.is_file():
        return _load_installation_identity(profile)
    client_instance_id = str(uuid.uuid4())
    if not CLIENT_INSTANCE_PATTERN.fullmatch(client_instance_id):
        raise CliError("Unable to create a safe Floeva installation identity.")
    identity = {
        "version": 1,
        "client_id": profile["client_id"],
        "client_instance_id": client_instance_id,
        "created_at": int(time.time()),
    }
    _atomic_write_json(path, identity)
    return identity


def _load_installation_identity(profile: dict[str, Any]) -> dict[str, Any]:
    path = _client_paths(profile)["instance"]
    if not isinstance(path, Path) or not path.is_file():
        raise CliError("Floeva installation is not initialized.")
    _require_private_file(path)
    identity = _load_json(path)
    instance_id = identity.get("client_instance_id")
    if (
        identity.get("version") != 1
        or identity.get("client_id") != profile["client_id"]
        or not isinstance(instance_id, str)
        or not CLIENT_INSTANCE_PATTERN.fullmatch(instance_id)
    ):
        raise CliError("Floeva installation identity is invalid.")
    return identity


def initialize_client(profile: dict[str, Any]) -> None:
    _ensure_installation_identity(profile)
    print("initialized")


def _start_authorization(profile: dict[str, Any], region: str) -> None:
    if region not in profile["regions"]:
        raise CliError("The selected region is not available for this Floeva client.")
    paths = _client_paths(profile)
    session_path = paths["session"]
    assert isinstance(session_path, Path)
    if not profile["dedicated_store"]:
        _purge_expired_session(session_path)
    identity = _ensure_installation_identity(profile) if profile["requires_instance"] else None
    base_url = profile["base_urls"][region]
    request_payload = {"client_id": profile["client_id"], "scope": SCOPE}
    if identity is not None:
        request_payload["client_instance_id"] = identity["client_instance_id"]
    status, response = _request_json(
        f"{base_url}/open/oauth/device/code", request_payload
    )
    if status != 200:
        raise CliError(f"Unable to start Floeva web authorization (HTTP {status}).")

    device_code = response.get("device_code")
    user_code = response.get("user_code")
    verification_uri = response.get("verification_uri")
    verification_complete = response.get("verification_uri_complete")
    if not all(
        isinstance(item, str) and item
        for item in (device_code, user_code, verification_uri)
    ):
        raise CliError("Floeva returned an incomplete authorization response.")
    expires_in = _positive_int(response.get("expires_in"), "expires_in")
    interval = _positive_int(response.get("interval", 5), "interval")
    _validate_verification_url(verification_uri, region, profile=profile)
    if verification_complete is not None:
        if not isinstance(verification_complete, str) or not verification_complete:
            raise CliError("Floeva returned an invalid authorization response.")
        _validate_verification_url(verification_complete, region, user_code, profile)
        verification_url = verification_complete
    else:
        verification_url = verification_uri

    session: dict[str, Any] = {
        "base_url": base_url,
        "client_id": profile["client_id"],
        "device_code": device_code,
        "expires_at": int(time.time()) + expires_in,
        "interval": interval,
        "last_poll_at": 0,
        "region": region,
    }
    if identity is not None:
        session["client_instance_id"] = identity["client_instance_id"]
    _atomic_write_json(session_path, session)
    if profile["dedicated_store"]:
        print(verification_url)
    else:
        print("Open this Floeva URL to authorize the Agent:")
        print(verification_url)
        print(f"Confirm code: {user_code}")
        print("After approval, run: floeva-auth.sh complete")


def start_authorization(region: str) -> None:
    if region not in REGIONS:
        raise CliError("Usage: floeva-auth.sh start <global|cn>")
    _start_authorization(_require_client_profile(LEGACY_CLIENT_ID), region)


def _load_session_for(
    profile: dict[str, Any], paths: dict[str, Path | None]
) -> dict[str, Any]:
    session_path = paths["session"]
    assert isinstance(session_path, Path)
    if not session_path.is_file():
        raise CliError("No pending Floeva authorization. Start one first.")
    try:
        _require_private_file(session_path)
        session = _load_json(session_path)
        region = session.get("region")
        if region not in profile["regions"]:
            raise CliError("The pending Floeva authorization is invalid.")
        if session.get("base_url") != profile["base_urls"][region]:
            raise CliError("The pending Floeva authorization has the wrong data region.")
        if session.get("client_id") != profile["client_id"]:
            raise CliError("The pending Floeva authorization has the wrong client.")
        if not isinstance(session.get("device_code"), str) or not session["device_code"]:
            raise CliError("The pending Floeva authorization is incomplete.")
        if profile["requires_instance"]:
            identity = _load_installation_identity(profile)
            if session.get("client_instance_id") != identity["client_instance_id"]:
                raise CliError("The pending Floeva authorization belongs to another installation.")
        session["expires_at"] = _positive_int(session.get("expires_at"), "expires_at")
        session["interval"] = _positive_int(session.get("interval"), "interval")
        session["last_poll_at"] = int(session.get("last_poll_at", 0))
        return session
    except (CliError, TypeError, ValueError):
        session_path.unlink(missing_ok=True)
        raise CliError("The pending Floeva authorization is invalid. Start again.")


def _load_session() -> dict[str, Any]:
    profile = _require_client_profile(LEGACY_CLIENT_ID)
    return _load_session_for(profile, _client_paths(profile))


def _complete_authorization(profile: dict[str, Any]) -> None:
    paths = _client_paths(profile)
    session_path = paths["session"]
    credential_path = paths["credential"]
    assert isinstance(session_path, Path) and isinstance(credential_path, Path)
    session = _load_session_for(profile, paths)
    now = int(time.time())
    if now >= session["expires_at"]:
        session_path.unlink(missing_ok=True)
        raise CliError("The Floeva authorization code expired. Start again.")
    if now < session["last_poll_at"] + session["interval"]:
        raise CliError("Floeva authorization is still pending.", exit_code=2)

    payload: dict[str, Any] = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": profile["client_id"],
        "device_code": session["device_code"],
    }
    if profile["requires_instance"]:
        payload["client_instance_id"] = session["client_instance_id"]
    status, response = _request_json(f"{session['base_url']}/open/oauth/token", payload)
    oauth_error = response.get("error")
    if status == 400 and oauth_error in {"authorization_pending", "slow_down"}:
        session["last_poll_at"] = now
        if oauth_error == "slow_down":
            session["interval"] += 5
        _atomic_write_json(session_path, session)
        raise CliError("Floeva authorization is still pending.", exit_code=2)
    if status != 200:
        error = oauth_error
        if error in {"access_denied", "expired_token", "invalid_grant"}:
            session_path.unlink(missing_ok=True)
        safe_error = error if isinstance(error, str) and error else f"HTTP {status}"
        raise CliError(f"Unable to complete Floeva authorization ({safe_error}).")

    access_token = response.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise CliError("Floeva returned an incomplete token response.")
    token_type = response.get("token_type")
    response_scope = response.get("scope", SCOPE)
    if not isinstance(token_type, str) or token_type.lower() != "bearer" or response_scope != SCOPE:
        raise CliError("Floeva returned an unexpected token contract.")
    expires_in = _positive_int(response.get("expires_in"), "expires_in")
    credential: dict[str, Any] = {
        "access_token": access_token,
        "auth_mode": "device_authorization",
        "base_url": session["base_url"],
        "expires_at": now + expires_in,
        "region": session["region"],
    }
    if profile["requires_instance"]:
        identity = _load_installation_identity(profile)
        if session.get("client_instance_id") != identity["client_instance_id"]:
            raise CliError("The Floeva authorization belongs to another installation.")
        credential["client_id"] = profile["client_id"]
        credential["client_instance_id"] = identity["client_instance_id"]
    _atomic_write_json(credential_path, credential)
    session_path.unlink(missing_ok=True)
    print("authorized" if profile["dedicated_store"] else "Floeva web authorization completed.")


def complete_authorization() -> None:
    _complete_authorization(_require_client_profile(LEGACY_CLIENT_ID))


def _credential_contract_is_valid(
    config: dict[str, Any], profile: dict[str, Any], identity: dict[str, Any] | None
) -> bool:
    region = config.get("region")
    valid = (
        isinstance(config.get("access_token"), str)
        and bool(config["access_token"])
        and config.get("auth_mode") == "device_authorization"
        and region in profile["regions"]
        and config.get("base_url") == profile["base_urls"].get(region)
    )
    if profile["requires_instance"]:
        valid = valid and identity is not None and config.get("client_id") == profile["client_id"]
        valid = valid and config.get("client_instance_id") == identity.get("client_instance_id")
    return bool(valid)


def _credential_status(profile: dict[str, Any], read_only: bool) -> None:
    paths = _client_paths(profile)
    credential_path = paths["credential"]
    session_path = paths["session"]
    assert isinstance(credential_path, Path) and isinstance(session_path, Path)
    if not read_only:
        _purge_expired_session(session_path)
    if not credential_path.is_file():
        print("missing")
        raise CliError("", exit_code=1)
    try:
        _require_private_file(credential_path)
        config = _load_json(credential_path)
        identity = _load_installation_identity(profile) if profile["requires_instance"] else None
    except CliError:
        print("expired")
        raise CliError("", exit_code=3)

    if _credential_contract_is_valid(config, profile, identity):
        try:
            expires_at = int(config.get("expires_at"))
        except (TypeError, ValueError):
            print("expired")
            raise CliError("", exit_code=3)
        if int(time.time()) >= expires_at - EXPIRY_SKEW_SECONDS:
            print("expired")
            raise CliError("", exit_code=3)
        print("oauth")
        return
    if not profile["requires_instance"] and isinstance(config.get("api_key"), str) and config["api_key"]:
        print("legacy")
        return
    has_token = isinstance(config.get("access_token"), str)
    print("expired" if has_token else "missing")
    raise CliError("", exit_code=3 if has_token else 1)


def credential_status() -> None:
    _credential_status(_require_client_profile(LEGACY_CLIENT_ID), read_only=False)


def _load_workbuddy_credential(
    profile: dict[str, Any], identity: dict[str, Any]
) -> dict[str, Any] | None:
    path = _client_paths(profile)["credential"]
    assert isinstance(path, Path)
    if not path.is_file():
        return None
    _require_private_file(path)
    credential = _load_json(path)
    if not _credential_contract_is_valid(credential, profile, identity):
        raise CliError("Floeva authorization state does not match this installation.")
    return credential


def logout_client(profile: dict[str, Any], local_only: bool = False) -> None:
    if not profile["requires_instance"]:
        raise CliError("Logout is only available for managed connector clients.")
    paths = _client_paths(profile)
    credential_path = paths["credential"]
    session_path = paths["session"]
    instance_path = paths["instance"]
    assert isinstance(credential_path, Path)
    assert isinstance(session_path, Path)
    assert isinstance(instance_path, Path)
    if not instance_path.is_file():
        if credential_path.is_file():
            raise CliError("Floeva installation identity is missing; local state was preserved.")
        _atomic_remove_files([session_path])
        print("local_state_removed" if local_only else "logged_out")
        return
    identity = _load_installation_identity(profile)
    credential = _load_workbuddy_credential(profile, identity)
    if credential is not None and not local_only:
        status, _ = _request_json(
            f"{credential['base_url']}/open/oauth/revoke",
            {},
            headers={"Authorization": f"Bearer {credential['access_token']}"},
        )
        if status != 200:
            raise CliError("Unable to revoke Floeva authorization; local state was preserved.")
    _atomic_remove_files([credential_path, session_path])
    print("local_state_removed" if local_only else "logged_out")


def purge_client(profile: dict[str, Any]) -> None:
    logout_client(profile)
    paths = _client_paths(profile)
    instance_path = paths["instance"]
    root = paths["root"]
    assert isinstance(instance_path, Path) and isinstance(root, Path)
    _atomic_remove_files([instance_path])
    try:
        root.rmdir()
    except OSError:
        pass
    print("purged")


def _parse_named_options(args: list[str], allowed: set[str]) -> dict[str, str]:
    if len(args) % 2 != 0:
        raise CliError("Invalid Floeva CLI arguments.")
    options: dict[str, str] = {}
    for index in range(0, len(args), 2):
        name = args[index]
        value = args[index + 1]
        if name not in allowed or not value or name in options:
            raise CliError("Invalid Floeva CLI arguments.")
        options[name] = value
    return options


def _profile_from_options(options: dict[str, str]) -> dict[str, Any]:
    return _require_client_profile(options.get("--client", LEGACY_CLIENT_ID))


def main(argv: list[str]) -> int:
    try:
        command = argv[1] if len(argv) > 1 else ""
        args = argv[2:]
        if command == "start" and len(args) == 1 and not args[0].startswith("--"):
            start_authorization(args[0])
        elif command == "start":
            options = _parse_named_options(args, {"--client", "--region"})
            profile = _profile_from_options(options)
            _start_authorization(profile, options.get("--region", ""))
        elif command == "complete":
            options = _parse_named_options(args, {"--client"})
            _complete_authorization(_profile_from_options(options))
        elif command == "status":
            options = _parse_named_options(args, {"--client"})
            profile = _profile_from_options(options)
            _credential_status(profile, read_only=profile["dedicated_store"])
        elif command == "init":
            options = _parse_named_options(args, {"--client"})
            initialize_client(_profile_from_options(options))
        elif command == "logout":
            options = _parse_named_options(args, {"--client"})
            logout_client(_profile_from_options(options))
        elif command == "cleanup-local":
            options = _parse_named_options(args, {"--client"})
            logout_client(_profile_from_options(options), local_only=True)
        elif command == "purge":
            options = _parse_named_options(args, {"--client"})
            purge_client(_profile_from_options(options))
        else:
            raise CliError(
                "Usage: floeva-auth.py <status|start|complete|init|logout|cleanup-local|purge>"
            )
        return 0
    except CliError as exc:
        if str(exc):
            print(str(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
