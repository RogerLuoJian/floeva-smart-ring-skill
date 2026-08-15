#!/usr/bin/env python3
"""Secure OAuth device authorization helper for the Floeva Agent Skill."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


CLIENT_ID = "floeva-smart-ring-skill"
SCOPE = "health:read"
USER_AGENT = "Floeva-Smart-Ring-Skill/1.0"
EXPIRY_SKEW_SECONDS = 60
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
CONFIG_DIR = Path.home() / ".floeva"
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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError) as exc:
        raise CliError(f"Floeva authorization state is unreadable: {path.name}.") from exc
    if not isinstance(payload, dict):
        raise CliError(f"Floeva authorization state is invalid: {path.name}.")
    return payload


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


def _validate_verification_url(
    url: str, region: str, user_code: str | None = None
) -> None:
    parsed = urlparse(url)
    expected_host = REGIONS[region]["verification_host"]
    query_code = parse_qs(parsed.query).get("user_code", [""])[0]
    query_is_valid = (
        not parsed.query
        if user_code is None
        else query_code.replace("-", "").upper()
        == user_code.replace("-", "").upper()
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


def _purge_expired_session() -> None:
    if not SESSION_FILE.is_file():
        return
    try:
        session = _load_json(SESSION_FILE)
        expires_at = int(session.get("expires_at"))
    except (CliError, TypeError, ValueError):
        SESSION_FILE.unlink(missing_ok=True)
        return
    if int(time.time()) >= expires_at:
        SESSION_FILE.unlink(missing_ok=True)


def start_authorization(region: str) -> None:
    if region not in REGIONS:
        raise CliError("Usage: floeva-auth.sh start <global|cn>")
    _purge_expired_session()
    base_url = REGIONS[region]["base_url"]
    status, response = _request_json(
        f"{base_url}/open/oauth/device/code",
        {"client_id": CLIENT_ID, "scope": SCOPE},
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
    _validate_verification_url(verification_uri, region)
    if verification_complete is not None:
        if not isinstance(verification_complete, str) or not verification_complete:
            raise CliError("Floeva returned an invalid authorization response.")
        _validate_verification_url(verification_complete, region, user_code)
        verification_url = verification_complete
    else:
        verification_url = verification_uri

    _atomic_write_json(
        SESSION_FILE,
        {
            "base_url": base_url,
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "expires_at": int(time.time()) + expires_in,
            "interval": interval,
            "last_poll_at": 0,
            "region": region,
        },
    )
    print("Open this Floeva URL to authorize the Agent:")
    print(verification_url)
    print(f"Confirm code: {user_code}")
    print("After approval, run: floeva-auth.sh complete")


def _load_session() -> dict[str, Any]:
    if not SESSION_FILE.is_file():
        raise CliError("No pending Floeva authorization. Start one first.")
    try:
        session = _load_json(SESSION_FILE)
        region = session.get("region")
        if region not in REGIONS:
            raise CliError("The pending Floeva authorization is invalid.")
        if session.get("base_url") != REGIONS[region]["base_url"]:
            raise CliError("The pending Floeva authorization has the wrong data region.")
        if session.get("client_id") != CLIENT_ID:
            raise CliError("The pending Floeva authorization has the wrong client.")
        if not isinstance(session.get("device_code"), str) or not session["device_code"]:
            raise CliError("The pending Floeva authorization is incomplete.")
        session["expires_at"] = _positive_int(session.get("expires_at"), "expires_at")
        session["interval"] = _positive_int(session.get("interval"), "interval")
        session["last_poll_at"] = int(session.get("last_poll_at", 0))
        return session
    except (CliError, TypeError, ValueError):
        SESSION_FILE.unlink(missing_ok=True)
        raise CliError("The pending Floeva authorization is invalid. Start again.")


def complete_authorization() -> None:
    session = _load_session()
    now = int(time.time())
    if now >= session["expires_at"]:
        SESSION_FILE.unlink(missing_ok=True)
        raise CliError("The Floeva authorization code expired. Start again.")
    if now < session["last_poll_at"] + session["interval"]:
        raise CliError("Floeva authorization is still pending.", exit_code=2)

    status, response = _request_json(
        f"{session['base_url']}/open/oauth/token",
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": CLIENT_ID,
            "device_code": session["device_code"],
        },
    )
    oauth_error = response.get("error")
    if status == 400 and oauth_error in {"authorization_pending", "slow_down"}:
        session["last_poll_at"] = now
        if oauth_error == "slow_down":
            session["interval"] += 5
        _atomic_write_json(SESSION_FILE, session)
        raise CliError("Floeva authorization is still pending.", exit_code=2)
    if status != 200:
        error = oauth_error
        if error in {"access_denied", "expired_token", "invalid_grant"}:
            SESSION_FILE.unlink(missing_ok=True)
        safe_error = error if isinstance(error, str) and error else f"HTTP {status}"
        raise CliError(f"Unable to complete Floeva authorization ({safe_error}).")

    access_token = response.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise CliError("Floeva returned an incomplete token response.")
    token_type = response.get("token_type")
    response_scope = response.get("scope", SCOPE)
    if (
        not isinstance(token_type, str)
        or token_type.lower() != "bearer"
        or response_scope != SCOPE
    ):
        raise CliError("Floeva returned an unexpected token contract.")
    expires_in = _positive_int(response.get("expires_in"), "expires_in")
    _atomic_write_json(
        CONFIG_FILE,
        {
            "access_token": access_token,
            "auth_mode": "device_authorization",
            "base_url": session["base_url"],
            "expires_at": now + expires_in,
            "region": session["region"],
        },
    )
    SESSION_FILE.unlink(missing_ok=True)
    print("Floeva web authorization completed.")


def credential_status() -> None:
    _purge_expired_session()
    if not CONFIG_FILE.is_file():
        print("missing")
        raise CliError("", exit_code=1)
    try:
        config = _load_json(CONFIG_FILE)
    except CliError:
        print("missing")
        raise CliError("", exit_code=1)

    has_oauth_token = isinstance(config.get("access_token"), str) and bool(
        config["access_token"]
    )
    oauth_region = config.get("region")
    oauth_contract_is_valid = (
        has_oauth_token
        and config.get("auth_mode") == "device_authorization"
        and oauth_region in REGIONS
        and config.get("base_url") == REGIONS[oauth_region]["base_url"]
    )
    if oauth_contract_is_valid:
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
    if isinstance(config.get("api_key"), str) and config["api_key"]:
        print("legacy")
        return
    if has_oauth_token:
        print("expired")
        raise CliError("", exit_code=3)
    print("missing")
    raise CliError("", exit_code=1)


def main(argv: list[str]) -> int:
    try:
        command = argv[1] if len(argv) > 1 else ""
        if command == "start":
            start_authorization(argv[2] if len(argv) > 2 else "")
        elif command == "complete":
            complete_authorization()
        elif command == "status":
            credential_status()
        else:
            raise CliError("Usage: floeva-auth.sh <status|start global|start cn|complete>")
        return 0
    except CliError as exc:
        if str(exc):
            print(str(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
