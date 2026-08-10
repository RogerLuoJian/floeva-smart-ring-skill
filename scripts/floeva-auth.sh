#!/bin/sh
set -eu

CLIENT_ID="floeva-smart-ring-skill"
SCOPE="health:read"
CONFIG_DIR="${HOME}/.floeva"
CONFIG_FILE="${CONFIG_DIR}/config.json"
SESSION_FILE="${CONFIG_DIR}/device-authorization.json"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '%s\n' "Required command not found: $1" >&2
    exit 1
  }
}

json_get() {
  python3 - "$1" "$2" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as handle:
    value = json.load(handle).get(key)
print("" if value is None else value)
PY
}

write_session() {
  python3 - "$SESSION_FILE" "$1" "$2" "$3" "$4" <<'PY'
import json, os, sys, time
path, base_url, device_code, client_id, expires_in = sys.argv[1:]
payload = {
    "base_url": base_url,
    "device_code": device_code,
    "client_id": client_id,
    "expires_at": int(time.time()) + int(expires_in),
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, separators=(",", ":"))
    handle.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY
}

write_config() {
  python3 - "$CONFIG_FILE" "$1" "$2" "$3" <<'PY'
import json, os, sys, time
path, base_url, response_path, region = sys.argv[1:]
with open(response_path, encoding="utf-8") as response_handle:
    response = json.load(response_handle)
access_token = response.get("access_token")
expires_in = response.get("expires_in")
if not access_token or expires_in is None:
    raise SystemExit("Floeva returned an incomplete token response.")
payload = {
    "auth_mode": "device_authorization",
    "access_token": access_token,
    "base_url": base_url,
    "expires_at": int(time.time()) + int(expires_in),
    "region": region,
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, separators=(",", ":"))
    handle.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY
}

start_authorization() {
  region="${1:-}"
  case "$region" in
    global) base_url="https://us.getfloeva.com/ring/api" ;;
    cn) base_url="https://server.floeva.cn/ring/api" ;;
    *) printf '%s\n' "Usage: floeva-auth.sh start <global|cn>" >&2; exit 1 ;;
  esac

  response_file=$(mktemp "${TMPDIR:-/tmp}/floeva-auth.XXXXXX")
  trap 'rm -f "$response_file"' EXIT HUP INT TERM
  http_code=$(curl -sS -m 30 -o "$response_file" -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "{\"client_id\":\"${CLIENT_ID}\",\"scope\":\"${SCOPE}\"}" \
    "${base_url}/open/oauth/device/code")
  if [ "$http_code" != "200" ]; then
    printf '%s\n' "Unable to start Floeva web authorization (HTTP ${http_code})." >&2
    exit 1
  fi

  device_code=$(json_get "$response_file" device_code)
  user_code=$(json_get "$response_file" user_code)
  verification_url=$(json_get "$response_file" verification_uri_complete)
  expires_in=$(json_get "$response_file" expires_in)
  [ -n "$device_code" ] && [ -n "$user_code" ] && [ -n "$verification_url" ] || {
    printf '%s\n' "Floeva returned an incomplete authorization response." >&2
    exit 1
  }
  mkdir -p "$CONFIG_DIR"
  chmod 700 "$CONFIG_DIR"
  write_session "$base_url" "$device_code" "$CLIENT_ID" "$expires_in"
  printf '%s\n' "Open this Floeva URL to authorize the Agent:"
  printf '%s\n' "$verification_url"
  printf '%s\n' "Confirm code: $user_code"
  printf '%s\n' "After approval, run: floeva-auth.sh complete"
}

complete_authorization() {
  [ -f "$SESSION_FILE" ] || {
    printf '%s\n' "No pending Floeva authorization. Start one first." >&2
    exit 1
  }
  base_url=$(json_get "$SESSION_FILE" base_url)
  device_code=$(json_get "$SESSION_FILE" device_code)
  client_id=$(json_get "$SESSION_FILE" client_id)
  expires_at=$(json_get "$SESSION_FILE" expires_at)
  now=$(date +%s)
  if [ -z "$device_code" ] || [ "$now" -ge "$expires_at" ]; then
    rm -f "$SESSION_FILE"
    printf '%s\n' "The Floeva authorization code expired. Start again." >&2
    exit 1
  fi

  response_file=$(mktemp "${TMPDIR:-/tmp}/floeva-token.XXXXXX")
  request_file=$(mktemp "${TMPDIR:-/tmp}/floeva-token-request.XXXXXX")
  trap 'rm -f "$response_file" "$request_file"' EXIT HUP INT TERM
  python3 - "$SESSION_FILE" "$request_file" <<'PY'
import json, os, sys
session_path, request_path = sys.argv[1:]
with open(session_path, encoding="utf-8") as handle:
    session = json.load(handle)
payload = {
    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    "device_code": session["device_code"],
    "client_id": session["client_id"],
}
with open(request_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, separators=(",", ":"))
os.chmod(request_path, 0o600)
PY
  http_code=$(curl -sS -m 30 -o "$response_file" -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    --data-binary "@${request_file}" \
    "${base_url}/open/oauth/token")
  if [ "$http_code" = "400" ] && [ "$(json_get "$response_file" error)" = "authorization_pending" ]; then
    printf '%s\n' "Floeva authorization is still pending." >&2
    exit 2
  fi
  if [ "$http_code" != "200" ]; then
    error=$(json_get "$response_file" error)
    [ "$error" = "expired_token" ] && rm -f "$SESSION_FILE"
    printf '%s\n' "Unable to complete Floeva authorization (${error:-HTTP $http_code})." >&2
    exit 1
  fi

  case "$base_url" in
    *server.floeva.cn*) region="cn" ;;
    *) region="global" ;;
  esac
  write_config "$base_url" "$response_file" "$region"
  rm -f "$SESSION_FILE"
  printf '%s\n' "Floeva web authorization completed."
}

require_command curl
require_command python3
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

case "${1:-}" in
  start) start_authorization "${2:-}" ;;
  complete) complete_authorization ;;
  *) printf '%s\n' "Usage: floeva-auth.sh <start global|start cn|complete>" >&2; exit 1 ;;
esac
