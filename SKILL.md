---
name: floeva-smart-ring
description: >
  Connect to Floeva health platform API. Use when the user wants to
  query health data, list available tools, execute health tools, or
  get a health overview from their Floeva smart ring. Triggers on:
  floeva, health data, smart ring, flow score, heart rate, HRV,
  sleep data, health overview, ring data.
allowed-tools:
  - Bash
  - Read
  - Write
---

# Floeva Smart Ring

Connect to the Floeva health platform to query smart ring health data, execute health tools, and get health overviews.

## Step 1: Load Configuration

Before making any API call, read the user's Floeva configuration:

```bash
cat ~/.floeva/config.json 2>/dev/null
```

If the file does not exist or does not contain `api_key`, go to **Step 2: First-Time Setup**. Otherwise, skip to **Step 3: Execute Request**.

## Step 2: First-Time Setup

If no API Key is configured, display this message to the user and ask them to provide their API Key:

> **Floeva API Key Required**
>
> To connect to your Floeva smart ring data, you need an API Key.
>
> How to get one:
> 1. Open Floeva App -> Profile -> Account & Security -> API Key
> 2. Create a new API Key
> 3. Copy the key (starts with `fv_sk_`)
>
> Please paste your API Key:

After the user provides the key, validate it:

```bash
API_KEY="<user_provided_key>"
curl -s -m 30 -w "\n%{http_code}" -H "Authorization: Bearer $API_KEY" \
  https://us.getfloeva.com/ring/api/open/v1/tool/list
```

- If HTTP 200: save the configuration and proceed to Step 3
- If not 200: tell the user the key is invalid, show the guidance message again

To save the configuration (create directory, write file, set permissions):

```bash
mkdir -p ~/.floeva && cat > ~/.floeva/config.json << ENDCONFIG
{
  "api_key": "$API_KEY",
  "base_url": "https://us.getfloeva.com/ring/api"
}
ENDCONFIG
chmod 600 ~/.floeva/config.json
```

## Step 3: Execute Request

Read `api_key` and `base_url` from `~/.floeva/config.json`:

```bash
if command -v python3 &>/dev/null; then
  API_KEY=$(python3 -c "import json; c=json.load(open('$HOME/.floeva/config.json')); print(c['api_key'])")
  BASE_URL=$(python3 -c "import json; c=json.load(open('$HOME/.floeva/config.json')); print(c['base_url'])")
else
  API_KEY=$(sed -n 's/.*"api_key"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' ~/.floeva/config.json)
  BASE_URL=$(sed -n 's/.*"base_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' ~/.floeva/config.json)
fi
```

Then match the user's intent to the appropriate endpoint.

### List Available Tools

When the user asks what tools/capabilities are available, or asks "what can Floeva do":

```bash
curl -s -m 30 -w "\n%{http_code}" -H "Authorization: Bearer $API_KEY" \
  "$BASE_URL/open/v1/tool/list"
```

Present the tool list to the user in a readable format — tool name, description, and parameters.

### Health Overview

When the user asks for a health summary, overview, or general health status:

```bash
curl -s -m 30 -w "\n%{http_code}" -H "Authorization: Bearer $API_KEY" \
  "$BASE_URL/open/v1/health/overview"
```

Present the health data in natural language — summarize key metrics like sleep quality, heart rate trends, step counts, and Flow score.

### Execute a Specific Tool

When the user asks for specific health data (e.g., "show my heart rate", "how did I sleep last night"):

1. If tool names are not already known from a prior call, first call **List Available Tools** to find the matching tool name and required parameters
2. Then execute:

```bash
curl -s -m 30 -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"toolName": "<tool_name>", "arguments": {<tool_arguments>}}' \
  "$BASE_URL/open/v1/tool/execute"
```

Present the results in natural language, interpreting health metrics meaningfully for the user.

## Step 4: Handle Errors

After every curl call, check the HTTP status code. The `-w "\n%{http_code}"` flag appends the HTTP status code as the last line of output — everything before it is the JSON response body.

### HTTP 401 — Invalid or Expired Key

Display:

> Your Floeva API Key is invalid or has expired. Please check your key status in Floeva App -> Profile -> Account & Security -> API Key, or generate a new one.

Then go back to **Step 2** to collect a new key. Validate the new key before saving.

### HTTP 429 — Rate Limited

Display:

> Daily API call limit reached. Please try again tomorrow, or check your quota in the Floeva App.

Do **NOT** re-prompt for a new key. This is a quota issue, not a key issue.

### Timeout or Network Error

If curl fails with a timeout or connection error:

> Unable to reach the Floeva server. Please check your network connection and try again.

### Other Errors

For any response where `code` is not 200, display the `msg` field from the response to the user.

## Response Format Reference

Success responses contain `code` and `data`:

```json
{
  "code": 200,
  "data": { ... }
}
```

Error responses contain `code` and `msg`:

```json
{
  "code": 401,
  "msg": "error description"
}
```

## Security Notes

- API Key is stored in `~/.floeva/config.json` with `chmod 600` permissions
- Always read the key into a shell variable (`$API_KEY`) — never hardcode it in curl commands
- The config file is independent of any AI Agent platform and shared across Claude Code, OpenClaw, and other tools
