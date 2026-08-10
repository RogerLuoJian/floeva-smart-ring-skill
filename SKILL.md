---
name: floeva-smart-ring
description: Connect to the Floeva health platform through secure web authorization. Use when the user wants to query smart-ring health data, list or execute Floeva health tools, get a health overview, or ask about Floeva ring setup, charging, waterproofing, warranty, FAQ, and troubleshooting. Triggers include Floeva, smart ring, Flow score, sleep, heart rate, HRV, health overview, ring data, help, FAQ, setup, and troubleshooting.
---

# Floeva Smart Ring

Use Floeva's official web authorization to access a user's smart-ring health data. Never ask the user to paste an API key or password into the Agent conversation.

## 1. Load configuration

Read `~/.floeva/config.json` if it exists. Accept either:

- Current config: `access_token`, `base_url`, `expires_at`, `auth_mode: "device_authorization"`
- Legacy config: `api_key`, `base_url`

Treat a legacy `api_key` as the Bearer token so existing users are not interrupted. Offer web reauthorization only when the user asks to upgrade or the credential fails.

If no credential exists, or the current token is expired, continue to web authorization.

## 2. Authorize on the Floeva website

Ask which Floeva service the user uses only when it is not already in config:

- **Global** — Floeva international App, `https://us.getfloeva.com/ring/api`
- **China** — 芙洛怡中国版, `https://server.floeva.cn/ring/api`

Locate `scripts/floeva-auth.sh` beside this `SKILL.md`. If the platform does not expose the skill directory, check these installed paths:

```bash
~/.codex/skills/floeva-smart-ring/scripts/floeva-auth.sh
~/.claude/skills/floeva-smart-ring/scripts/floeva-auth.sh
~/.openclaw/skills/floeva-smart-ring/scripts/floeva-auth.sh
```

Start authorization with `global` or `cn`:

```bash
bash <skill-dir>/scripts/floeva-auth.sh start global
```

Show the returned Floeva URL and user code. Ask the user to open the URL, confirm the matching code, sign in on the Floeva-owned page, and tell you when approval is complete. Do not ask for their password.

After the user confirms, complete the exchange:

```bash
bash <skill-dir>/scripts/floeva-auth.sh complete
```

- Exit `0`: authorization succeeded; continue to the request.
- Exit `2`: approval is still pending; ask the user to finish the website step and retry once they confirm.
- Any other nonzero exit: show the script's safe error message. Restart authorization if the code expired.

Do not poll in a long blocking loop. The two-step interaction keeps authorization visible and gives the user control.

## 3. Execute requests

Read the credential without printing it:

```bash
if command -v python3 >/dev/null 2>&1; then
  ACCESS_TOKEN=$(python3 -c "import json,os; c=json.load(open(os.path.expanduser('~/.floeva/config.json'))); print(c.get('access_token') or c.get('api_key') or '')")
  BASE_URL=$(python3 -c "import json,os; c=json.load(open(os.path.expanduser('~/.floeva/config.json'))); print(c['base_url'])")
else
  ACCESS_TOKEN=$(sed -n 's/.*"\(access_token\|api_key\)"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\2/p' ~/.floeva/config.json | head -n 1)
  BASE_URL=$(sed -n 's/.*"base_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' ~/.floeva/config.json)
fi
```

Always send `Authorization: Bearer $ACCESS_TOKEN` over HTTPS.

### List capabilities

```bash
curl -sS -m 30 -w "\n%{http_code}" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$BASE_URL/open/v1/tool/list"
```

Present tool names, descriptions, and parameters clearly.

### Health overview

```bash
curl -sS -m 30 -w "\n%{http_code}" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$BASE_URL/open/v1/health/overview"
```

Summarize sleep, heart-rate trends, steps, and Flow score in warm, non-diagnostic language.

### Help and FAQ

```bash
curl -sS -m 30 -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"toolName":"get_help","arguments":{"query":"<keywords>","language":"zh"}}' \
  "$BASE_URL/open/v1/tool/execute"
```

Optional `get_help` arguments:

- `query`: keywords such as `charging`, `waterproof`, or `sleep`
- `category`: `product-basics`, `pre-purchase`, `setup-connection`, `wearing-guide`, `features-tracking`, `battery-charging`, `waterproof-durability`, `troubleshooting`, `health-safety`, `pricing-subscription`, or `tech-specs`
- `language`: `zh` or `en`

### Execute a specific health tool

If the tool contract is unknown, list capabilities first. Then call:

```bash
curl -sS -m 30 -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"toolName":"<tool_name>","arguments":{<tool_arguments>}}' \
  "$BASE_URL/open/v1/tool/execute"
```

Interpret the result for the user; do not present raw health data as a medical diagnosis.

## 4. Handle errors

The final line emitted by each request is the HTTP status.

- `401`: run `floeva-auth.sh start <region>` and guide the user through web authorization again. Do not request an API key.
- `429`: explain that the daily call limit is reached; do not reauthorize.
- Timeout/network failure: ask the user to retry after checking connectivity.
- Other errors: show the response `msg` without exposing the credential or config file.

## Security rules

- Never ask for, echo, log, or include Floeva passwords or tokens in conversation output.
- Store authorization data only in `~/.floeva/config.json` with mode `0600`.
- Never put access tokens in URLs, query strings, source files, or shell history.
- Use only the verification URL returned by the Floeva API and only HTTPS Floeva domains.
- Remove the short-lived `~/.floeva/device-authorization.json` after success or expiry.
