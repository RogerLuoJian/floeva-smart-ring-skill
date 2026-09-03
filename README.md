# Floeva Smart Ring Skill

An official Agent skill for securely connecting to [Floeva](https://getfloeva.com) smart-ring health data.

## What it does

- Opens a Floeva-owned webpage for authorization—no API key copy/paste
- Reads health overviews, sleep, heart rate, HRV, steps, and Flow score
- Opens an immersive Floeva Health Canvas with a rhythm landscape, insight rail,
  sleep structure, activity trace, and heart-range portrait
- Falls back to compact health snapshots, readable trend tables, and accessible
  sparklines when a local browser is unavailable
- Discovers and executes available health tools
- Answers product help and troubleshooting questions
- Supports Floeva Global and 芙洛怡 China data planes

## Install

Clone the repository, then run the installer:

```bash
git clone https://github.com/RogerLuoJian/floeva-smart-ring-skill.git
cd floeva-smart-ring-skill
./install.sh
```

The installer must run from a complete repository checkout; it does not execute
or assemble runtime files from a mutable remote branch. It detects Codex,
Claude Code, and OpenClaw, validates the checked-out files, and installs the
skill instructions, UI metadata, web-authorization helper, local report
runtime, bundled fonts, and Floeva-owned visual assets.

## Use

Start a new Agent session and ask naturally:

- “Show my Floeva health overview.”
- “把我的健康数据做成漂亮的可视化报告。”
- “How did I sleep last night?”
- “What is my heart-rate trend?”
- “How do I charge my Floeva ring?”

For a complete overview, the Skill opens a private local Health Canvas when a
browser is available. The Canvas is an original Floeva presentation: a spacious
lavender-to-warm-peach rhythm landscape paired with a frosted insight rail,
rather than a generic analytics chart. Health answers still lead with a useful
observation in the conversation. Missing sensor data stays visibly distinct
from a recorded zero, and personal-baseline comparisons appear only after
Floeva has enough data to establish one.

On first use, the Agent asks whether you use Floeva Global or China, then gives you a 10-minute Floeva website link and matching code. Sign in on that page, approve, and return to the Agent. The resulting access token is valid for up to 90 days and can be revoked from Floeva's API credential management screen.

Authorization is stored in `~/.floeva/config.json` with file mode `0600`. The access token is time-limited and can be replaced by authorizing again. Existing legacy `api_key` configs remain supported during migration.

## Configuration

New web authorizations use:

```json
{
  "access_token": "<secret>",
  "auth_mode": "device_authorization",
  "base_url": "https://us.getfloeva.com/ring/api",
  "expires_at": 1780000000,
  "region": "global"
}
```

Existing configs containing `api_key` and `base_url` continue to work unchanged. The installer and helper never overwrite a legacy config unless web authorization completes and the new token is safely stored.

## Security

- Passwords stay on the Floeva-owned authorization page and are never shared with the Agent.
- Access tokens and pending device codes are stored only under `~/.floeva` with restricted permissions.
- Config updates use an atomic replace, so an interrupted authorization does not corrupt an existing credential.
- Verification links are accepted only from the expected HTTPS Floeva domain for the selected region.
- Visual reports bind only to `127.0.0.1`, use opaque session URLs, expire after
  one hour, and are stored under `~/.floeva/reports` with private permissions.
- Only health response data enters the browser report. Access tokens, API keys,
  passwords, device codes, config files, and remote API URLs do not.
- The report uses bundled local fonts and assets; it makes no third-party web
  requests and disables caching, referrers, and framing.

## WorkBuddy connector development

The repository also contains the China-only WorkBuddy connector implementation:

- `scripts/floeva-auth.py` supports the allowlisted `floeva-workbuddy-cn`
  client with a stable random installation identity and isolated credential
  store.
- `mcp/` contains the Node 20 stdio MCP adapter and its locked dependencies.
- `workbuddy/cn/` contains reviewed metadata, the Floeva icon, and the MCP-only
  Skill overlay. `workbuddy/build_connector.py` assembles a deterministic
  review archive after the WorkBuddy configuration gates are approved.

Development checks:

```bash
python3 -m unittest discover -s tests
cd mcp && npm ci && npm test && npm run build && npm audit
```

The release builder intentionally refuses to create a zip until
`gate-approval.json` binds exact `mcp.json` and `cli.json` hashes to official
WorkBuddy Device Flow schema and packaged-runtime path evidence. This prevents
shipping guessed `authDeviceFlow` fields or per-device client IDs.

## Uninstall

```bash
rm -rf ~/.codex/skills/floeva-smart-ring
rm -rf ~/.claude/skills/floeva-smart-ring
rm -rf ~/.openclaw/skills/floeva-smart-ring
rm -rf ~/.floeva  # optional: removes authorization data
```

## License

MIT
