---
name: floeva-smart-ring
description: Connect to the Floeva health platform through secure web authorization. Use when the user wants to query smart-ring health data, open an immersive visual health report, list or execute Floeva health tools, get a health overview, or ask about Floeva ring setup, charging, waterproofing, warranty, FAQ, and troubleshooting. Triggers include Floeva, smart ring, Flow score, sleep, heart rate, HRV, health overview, health dashboard, charts, ring data, help, FAQ, setup, and troubleshooting.
---

# Floeva Smart Ring

Use Floeva's official web authorization to access a user's smart-ring health data. Never ask the user to paste an API key or password into the Agent conversation.

## 1. Load configuration

Locate `scripts/floeva-auth.sh` beside this `SKILL.md`. If the platform does not expose the skill directory, check these installed paths:

```bash
~/.codex/skills/floeva-smart-ring/scripts/floeva-auth.sh
~/.claude/skills/floeva-smart-ring/scripts/floeva-auth.sh
~/.openclaw/skills/floeva-smart-ring/scripts/floeva-auth.sh
```

The same skill directory also contains `scripts/floeva-report.py` and the
`assets/health-report/` visual runtime. Never use a report helper or assets from
another directory.

Check credential status without printing the config or secret:

```bash
bash <skill-dir>/scripts/floeva-auth.sh status
```

- `oauth` with exit `0`: use the current `access_token`.
- `legacy` with exit `0`: use the current `api_key` unchanged.
- `expired` with exit `3`: continue to web authorization. Reuse the saved region.
- `missing` with exit `1`: continue to web authorization.

Accept either config shape:

- Current config: `access_token`, `base_url`, `expires_at`, `auth_mode: "device_authorization"`
- Legacy config: `api_key`, `base_url`

Never display or `cat` the config file. Treat a legacy `api_key` as the Bearer token so existing users are not interrupted. Offer web reauthorization only when the user asks to upgrade or the credential fails.

## 2. Authorize on the Floeva website

Ask which Floeva service the user uses only when it is not already in config:

- **Global** — Floeva international App, `https://us.getfloeva.com/ring/api`
- **China** — 芙洛怡中国版, `https://server.floeva.cn/ring/api`

Start authorization with `global` or `cn`:

```bash
bash <skill-dir>/scripts/floeva-auth.sh start global
```

Show the returned Floeva URL and user code. Ask the user to open the URL, confirm the matching code, sign in on the Floeva-owned page, and tell you when approval is complete. Do not ask for their password.

After the user confirms, complete the exchange:

```bash
bash <skill-dir>/scripts/floeva-auth.sh complete
```

- Exit `0`: authorization succeeded; continue to the request. The credential is valid for up to 90 days.
- Exit `2`: approval is still pending; ask the user to finish the website step and retry once they confirm.
- Any other nonzero exit: show the script's safe error message. Restart authorization if the code expired.

Do not poll in a long blocking loop. The two-step interaction keeps authorization visible and gives the user control.

## 3. Execute requests

After `status` returns `oauth` or `legacy`, read the credential into shell variables without printing it:

```bash
ACCESS_TOKEN=$(python3 -c "import json,os; c=json.load(open(os.path.expanduser('~/.floeva/config.json'))); print(c.get('access_token') or c.get('api_key') or '')")
BASE_URL=$(python3 -c "import json,os; c=json.load(open(os.path.expanduser('~/.floeva/config.json'))); print(c['base_url'])")
AUTH_MODE=$(python3 -c "import json,os; c=json.load(open(os.path.expanduser('~/.floeva/config.json'))); print(c.get('auth_mode') or 'legacy')")
```

Always send `Authorization: Bearer $ACCESS_TOKEN` over HTTPS.

Before presenting any successful health-data response, read
`references/data-presentation.md` completely. Use its hierarchy, units,
missing-data rules, and compact Markdown templates. Lead with the finding,
not the endpoint or raw JSON. When the request is an overview or mentions a
dashboard, chart, graph, visual, or prettier presentation, also read
`references/health-canvas.md` completely and follow the visual workflow below.

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

Summarize sleep, heart-rate trends, steps, and available baseline context in
warm, non-diagnostic language. For a complete overview that includes Flow, or
whenever the user asks about Flow, also execute `get_flow_score_detail` for the
requested date. Pass the user's IANA timezone when it is known. Do not infer a
Flow score from the other health metrics.

### Immersive visual report

For a complete health overview, automatically attempt the Floeva Health Canvas
when a local browser is available, unless the user asks for text only. Always
use it when the user explicitly requests a dashboard, chart, graph, visual
report, or more beautiful presentation.

Prepare the private report directly from the authorized Floeva service:

```bash
python3 <skill-dir>/scripts/floeva-report.py prepare
```

This command prints one non-secret JSON object containing the random local URL,
session id, expiry, and a compact summary. It must not print the credential or
raw config. Start or safely reuse the localhost server exactly as specified in
`references/health-canvas.md`, then open the returned URL for the user. Do not
replace this Canvas with a generic chart library when the report runtime is
available.

In the conversation, lead with one useful finding and mention that the opened
visual report is private to this device and expires in one hour. If the local
browser or report runtime is unavailable, fall back to the compact Markdown
view without claiming that an immersive report was created.

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
Apply the presentation contract to specific-tool results too. Prefer a compact
trend table or sparkline for comparable dated values, and show data coverage
beside any interpretation that depends on sample count or days recorded.

## 4. Handle errors

The final line emitted by each request is the HTTP status.

- `401` with `AUTH_MODE=device_authorization`: restart web authorization in the saved region.
- `401` with `AUTH_MODE=legacy`: explain that the legacy credential no longer works and offer web authorization. Do not ask the user to paste another API key.
- `429`: explain that the daily call limit is reached; do not reauthorize.
- Timeout/network failure: ask the user to retry after checking connectivity.
- Other errors: show the response `msg` without exposing the credential or config file.

## Security rules

- Never ask for, echo, log, or include Floeva passwords or tokens in conversation output.
- Store authorization data only in `~/.floeva/config.json` with mode `0600`.
- Never put access tokens in URLs, query strings, source files, or shell history.
- Use only the verification URL returned by the Floeva API and only HTTPS Floeva domains.
- Remove the short-lived `~/.floeva/device-authorization.json` after success or expiry.
- Keep visual-report data under `~/.floeva/reports` only; never upload it or
  expose its localhost server beyond `127.0.0.1`.
- Never include an access token, API key, config file, device code, or remote
  API URL in a browser report. Remove the exact report session when it is no
  longer needed; expired sessions are automatically purged.
- Do not replace a working legacy config until web authorization succeeds and the new config is atomically stored.
