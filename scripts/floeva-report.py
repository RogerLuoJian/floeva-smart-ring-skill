#!/usr/bin/env python3
"""Prepare and serve a private, local Floeva health report."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


USER_AGENT = "Floeva-Smart-Ring-Skill/1.0"
REPORT_HOST = "127.0.0.1"
REPORT_PORT = 5176
REPORT_TTL_SECONDS = 60 * 60
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ALLOWED_BASE_URLS = {
    "https://us.getfloeva.com/ring/api": "global",
    "https://server.floeva.cn/ring/api": "cn",
}
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32}$")
SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = SKILL_ROOT / "assets" / "health-report"
CONFIG_DIR = Path.home() / ".floeva"
CONFIG_FILE = CONFIG_DIR / "config.json"
REPORTS_DIR = CONFIG_DIR / "reports"
REQUIRED_ASSETS = (
    "index.html",
    "app.css",
    "app.js",
    "logo-icon.svg",
    "lotus.svg",
    "fonts/Inter-Regular.ttf",
    "fonts/Inter-Bold.ttf",
)
ASSET_CONTENT_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "logo-icon.svg": "image/svg+xml",
    "lotus.svg": "image/svg+xml",
    "fonts/Inter-Regular.ttf": "font/ttf",
    "fonts/Inter-Bold.ttf": "font/ttf",
}


class CliError(Exception):
    """A safe command-line error that never contains credentials."""


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
            json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False)
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
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise CliError(f"Unable to read {path.name}.") from exc
    if not isinstance(payload, dict):
        raise CliError(f"Invalid {path.name}.")
    return payload


def _load_config() -> tuple[str, str, str]:
    if not CONFIG_FILE.is_file():
        raise CliError("Floeva authorization is missing. Authorize first.")
    config = _load_json(CONFIG_FILE)
    base_url = config.get("base_url")
    if base_url not in ALLOWED_BASE_URLS:
        raise CliError("Floeva authorization has an invalid data region.")
    region = ALLOWED_BASE_URLS[base_url]
    configured_region = config.get("region")
    if configured_region is not None and configured_region != region:
        raise CliError("Floeva authorization has a mismatched data region.")
    token = config.get("access_token") or config.get("api_key")
    if not isinstance(token, str) or not token:
        raise CliError("Floeva authorization is missing. Authorize first.")
    if config.get("access_token"):
        try:
            expires_at = int(config.get("expires_at"))
        except (TypeError, ValueError) as exc:
            raise CliError("Floeva web authorization is expired. Authorize again.") from exc
        if int(time.time()) >= expires_at - 60:
            raise CliError("Floeva web authorization is expired. Authorize again.")
    return token, base_url, region


def _fetch_health_overview() -> tuple[dict[str, Any], str]:
    token, base_url, region = _load_config()
    request = urllib.request.Request(
        f"{base_url}/open/v1/health/overview",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            status = response.status
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.URLError as exc:
        raise CliError("Unable to reach the Floeva health service.") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise CliError("Floeva returned a health response that is too large.")
    if status != 200:
        if status == 401:
            raise CliError("Floeva authorization is no longer valid. Authorize again.")
        if status == 429:
            raise CliError("The Floeva daily request limit has been reached.")
        raise CliError(f"Floeva health service returned HTTP {status}.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CliError("Floeva returned an unreadable health response.") from exc
    if not isinstance(payload, dict):
        raise CliError("Floeva returned an invalid health response.")
    return payload, region


def _extract_health_data(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("code") != 200 or not isinstance(payload.get("data"), dict):
        message = payload.get("msg")
        if isinstance(message, str) and message:
            raise CliError(f"Floeva health request failed: {message}")
        raise CliError("Floeva returned an incomplete health response.")
    return payload["data"]


def _dated_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = [item for item in value if isinstance(item, dict)]
    return sorted(rows, key=lambda item: str(item.get("date") or ""))


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[-1] if rows else {}


def _build_summary(data: dict[str, Any]) -> dict[str, Any]:
    steps = _dated_rows((data.get("steps_7d") or {}).get("data"))
    heart = _dated_rows((data.get("heart_rate_7d") or {}).get("data"))
    sleep = _dated_rows((data.get("last_sleep") or {}).get("data"))
    daily = _dated_rows((data.get("daily_summary") or {}).get("data"))
    latest_steps = _latest(steps)
    latest_sleep = _latest(sleep)
    latest_daily = _latest(daily)
    recovery = latest_daily.get("stress_recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    baseline = data.get("baseline")
    if not isinstance(baseline, dict):
        baseline = {}
    dates = [
        str(item.get("date"))
        for item in (latest_steps, _latest(heart), latest_sleep, latest_daily)
        if item.get("date")
    ]
    return {
        "latest_date": max(dates) if dates else None,
        "coverage": {
            "steps_days": len(steps),
            "heart_days": len(heart),
            "sleep_days": len(sleep),
        },
        "latest": {
            "steps": latest_steps.get("steps"),
            "sleep_minutes": latest_sleep.get("total_minutes"),
            "hrv": recovery.get("avg_hrv"),
            "resting_heart_rate": recovery.get("resting_hr"),
        },
        "baseline": {
            "is_personalized": baseline.get("is_personalized") is True,
            "days_of_data": baseline.get("days_of_data"),
        },
    }


def _session_path(session: str) -> Path:
    if not SESSION_PATTERN.fullmatch(session):
        raise CliError("Invalid Floeva report session.")
    return REPORTS_DIR / session


def _remove_session(session: str) -> None:
    session_dir = _session_path(session)
    if session_dir.is_dir():
        shutil.rmtree(session_dir)


def cleanup_expired(now: int | None = None) -> int:
    current = int(time.time()) if now is None else now
    if not REPORTS_DIR.is_dir():
        return 0
    removed = 0
    for path in REPORTS_DIR.iterdir():
        if not path.is_dir() or not SESSION_PATTERN.fullmatch(path.name):
            continue
        report_file = path / "report.json"
        try:
            payload = _load_json(report_file)
            expires_at = int(payload.get("expires_at"))
        except (CliError, TypeError, ValueError):
            shutil.rmtree(path)
            removed += 1
            continue
        if current >= expires_at:
            shutil.rmtree(path)
            removed += 1
    return removed


def prepare_report(
    payload: dict[str, Any],
    region: str,
    port: int = REPORT_PORT,
    now: int | None = None,
) -> dict[str, Any]:
    current = int(time.time()) if now is None else now
    data = _extract_health_data(payload)
    cleanup_expired(current)
    REPORTS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(REPORTS_DIR, 0o700)
    session = secrets.token_urlsafe(24)
    if not SESSION_PATTERN.fullmatch(session):
        raise CliError("Unable to create a secure Floeva report session.")
    session_dir = _session_path(session)
    session_dir.mkdir(mode=0o700)
    os.chmod(session_dir, 0o700)
    expires_at = current + REPORT_TTL_SECONDS
    _atomic_write_json(
        session_dir / "report.json",
        {
            "version": 1,
            "generated_at": current,
            "expires_at": expires_at,
            "region": region,
            "data": data,
        },
    )
    return {
        "url": f"http://{REPORT_HOST}:{port}/report/{session}/",
        "session": session,
        "expires_at": expires_at,
        "summary": _build_summary(data),
    }


def _load_report(session: str, now: int | None = None) -> dict[str, Any] | None:
    try:
        report_file = _session_path(session) / "report.json"
    except CliError:
        return None
    if not report_file.is_file():
        return None
    try:
        report = _load_json(report_file)
        expires_at = int(report.get("expires_at"))
    except (CliError, TypeError, ValueError):
        _remove_session(session)
        return None
    current = int(time.time()) if now is None else now
    if current >= expires_at:
        _remove_session(session)
        return None
    return report


def _asset_bytes(name: str) -> bytes:
    if name not in ASSET_CONTENT_TYPES:
        raise CliError("Unknown Floeva report asset.")
    path = ASSET_DIR / name
    if not path.is_file():
        raise CliError(f"Floeva report asset is missing: {name}.")
    return path.read_bytes()


def _check_assets() -> None:
    missing = [name for name in REQUIRED_ASSETS if not (ASSET_DIR / name).is_file()]
    if missing:
        raise CliError("Floeva report runtime is incomplete. Reinstall the Skill.")


def _handler_class() -> type[BaseHTTPRequestHandler]:
    route_pattern = re.compile(
        r"^/report/([A-Za-z0-9_-]{32})/(|report\.json|app\.css|app\.js|"
        r"logo-icon\.svg|lotus\.svg|fonts/Inter-(?:Regular|Bold)\.ttf)$"
    )

    class ReportHandler(BaseHTTPRequestHandler):
        server_version = "FloevaHealthCanvas/1.0"

        def log_message(self, format_string: str, *args: Any) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=(), payment=()",
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self._headers(status, content_type, len(body))
            if self.command != "HEAD":
                self.wfile.write(body)

        def _not_found(self) -> None:
            self._send(404, "text/plain; charset=utf-8", b"Not found\n")

        def _serve(self) -> None:
            expected_host = f"{REPORT_HOST}:{self.server.server_address[1]}"
            if self.headers.get("Host") != expected_host:
                self._send(421, "text/plain; charset=utf-8", b"Misdirected request\n")
                return
            parsed = urlparse(self.path)
            if parsed.query or parsed.fragment:
                self._not_found()
                return
            if parsed.path == "/healthz":
                body = b'{"app":"floeva-health-canvas","status":"ok"}\n'
                self._send(200, "application/json; charset=utf-8", body)
                return
            match = route_pattern.fullmatch(parsed.path)
            if not match:
                self._not_found()
                return
            session, asset_name = match.groups()
            report = _load_report(session)
            if report is None:
                self._not_found()
                return
            if asset_name == "report.json":
                body = json.dumps(
                    report, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
                return
            name = asset_name or "index.html"
            try:
                body = _asset_bytes(name)
            except CliError:
                self._not_found()
                return
            self._send(200, ASSET_CONTENT_TYPES[name], body)

        def do_GET(self) -> None:
            self._serve()

        def do_HEAD(self) -> None:
            self._serve()

    return ReportHandler


def create_server(port: int = REPORT_PORT) -> ThreadingHTTPServer:
    _check_assets()
    server = ThreadingHTTPServer((REPORT_HOST, port), _handler_class())
    server.daemon_threads = True
    return server


def _prepare_command(args: argparse.Namespace) -> None:
    if args.input:
        payload = _load_json(Path(args.input))
        region = args.region
    else:
        payload, region = _fetch_health_overview()
    result = prepare_report(payload, region, port=args.port)
    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))


def _serve_command(args: argparse.Namespace) -> None:
    cleanup_expired()
    try:
        server = create_server(args.port)
    except OSError as exc:
        raise CliError(
            f"Unable to start Floeva Health Canvas on {REPORT_HOST}:{args.port}."
        ) from exc
    print(
        f"READY http://{REPORT_HOST}:{server.server_address[1]}/ "
        "Floeva Health Canvas",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _cleanup_command(args: argparse.Namespace) -> None:
    if args.session:
        _remove_session(args.session)
        print("Floeva report session removed.")
    else:
        removed = cleanup_expired()
        print(f"Removed {removed} expired Floeva report session(s).")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Floeva Health Canvas runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="stage a private health report")
    prepare.add_argument("--input", help="read a saved health-overview response")
    prepare.add_argument("--region", choices=("global", "cn"), default="global")
    prepare.add_argument("--port", type=int, default=REPORT_PORT)

    serve = subparsers.add_parser("serve", help="serve reports on localhost")
    serve.add_argument("--port", type=int, default=REPORT_PORT)

    cleanup = subparsers.add_parser("cleanup", help="remove one or expired reports")
    cleanup.add_argument("session", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "prepare":
            _prepare_command(args)
        elif args.command == "serve":
            _serve_command(args)
        else:
            _cleanup_command(args)
        return 0
    except CliError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
