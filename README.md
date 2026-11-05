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

Use the same package for any Agent that supports standard `SKILL.md` skills
and can run Bash and Python 3 with network access. Pick a directory that your
Agent actually discovers; Floeva does not need a new adapter or Agent registry.

Clone the complete repository, then specify the **full destination Skill directory**:

```bash
git clone https://github.com/RogerLuoJian/floeva-smart-ring-skill.git
cd floeva-smart-ring-skill
./install.sh --target "$HOME/.agents/skills/floeva-smart-ring"
```

`~/.agents/skills/` is a shared-directory convention, not a guarantee that every
Agent discovers it automatically. Configure your Agent to scan that directory,
or pass its native Skill directory instead. For example, with Hermes's default
profile:

```bash
./install.sh --target "$HOME/.hermes/skills/floeva-smart-ring"
```

Relative destinations and paths containing spaces are supported. An explicit
`--target` installs only there, even if other Agents are installed. The target
includes `floeva-smart-ring`; it is not the parent `skills/` directory. Run
`./install.sh --help` for usage.

For backward compatibility, `./install.sh` without options still installs into
all existing `~/.codex`, `~/.claude`, and `~/.openclaw` Skill directories. If none
exist, it installs into `~/.agents/skills/floeva-smart-ring`. These are convenience
shortcuts; future Agents use `--target` without changing Floeva code.

The installer runs from a complete local checkout, validates the checked-out
files, and installs the instructions, UI metadata, authorization helper, local
report runtime, fonts, and visual assets together. Do not copy only `SKILL.md`.
It does not execute or assemble runtime files from a mutable remote branch.
Re-run the same command from an updated checkout to update that destination.

**Verify discovery separately:** the installer's success message confirms that
files were copied. Use your Agent's Skill listing/loading mechanism to confirm
it discovers `floeva-smart-ring`, then ask for a health overview in a new session.
The Skill resolves its helpers relative to its own location, regardless of Agent.
Visual reports need a local browser on the runtime host; remote or headless
Agents use the text fallback when the local Canvas is inaccessible.

For an Agent to help with installation, give it this prompt:

```text
Install the official Floeva Skill from:
https://github.com/RogerLuoJian/floeva-smart-ring-skill
Read the README and clone the complete repository. Determine the Skill directory
for this Agent, then run install.sh --target <full-destination-skill-directory>.
Confirm this Agent can discover the Skill. On first use, declare your actual
Agent product name for Floeva authorization; do not infer it from the path.
```

This generic contract covers file-based Skill hosts; a platform requiring a
reviewed connector package still uses its platform packaging, such as WorkBuddy
below. Compatibility of the format does not replace actual host integration tests.

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

New Agent integrations declare their own product name with `--agent-name`.
Any valid declared product name is accepted without adding it to a registry.
The official shared client creates a stable random installation identity and keeps each Agent's credential and pending
session under a private hashed `~/.floeva/agents/<hash>/` scope, so a new
authorization cannot replace another Agent's connection. The product name is
explicitly supplied by the Agent; it is never guessed from the host or runtime.
Existing no-flag installations remain compatible with their legacy
`~/.floeva/config.json` / `api_key` migration path.

For an Agent-aware integration, use the same declared name for every command.
Replace `<declared-agent-name>` below with the actual product name, not the
literal placeholder:

```bash
python3 scripts/floeva-auth.py status --agent-name '<declared-agent-name>'
python3 scripts/floeva-auth.py start --agent-name '<declared-agent-name>' --region global
python3 scripts/floeva-auth.py complete --agent-name '<declared-agent-name>'
python3 scripts/floeva-auth.py overview --agent-name '<declared-agent-name>'
python3 scripts/floeva-report.py prepare --agent-name '<declared-agent-name>'
```

Use the helper for `tools`, `call`, `overview`, `logout`, and reports; do not
read credential files or make direct HTTP calls. If the Agent cannot state its
product name, it must ask the user before authorizing.

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
- Declared Agent products use a stable random `client_instance_id`, sent with
  their Device Flow requests alongside the declared `agent_name`; their hashed
  local storage scopes prevent cross-Agent credential or pending-session reuse.
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
  store. Its managed `auth` command completes Device Flow polling, while
  `tools`, `overview`, and `call` expose only allowlisted read-only health
  operations as JSON.
- `workbuddy/cn/` contains the documented Python runtime `cli.json`, reviewed
  metadata, the Floeva icon, and the CLI-only Skill overlay.
- `workbuddy/build_connector.py` validates the CLI contract and assembles a
  deterministic review archive from the canonical script and Skill sources.

Development checks:

```bash
python3 -m unittest discover -s tests
python3 workbuddy/build_connector.py
```

The connector uses WorkBuddy's documented CLI + Skill structure. WorkBuddy
provides Python 3.11, calls `init/auth/status/unAuth`, opens only the declared
`floeva.cn` authorization domain, and matches the side-effect-free `oauth`
status. The Skill invokes the packaged CLI through Bash and never reads or
prints credential files.

## Uninstall

Remove the exact directory passed to `--target`. For the shared-directory example:

```bash
rm -rf ~/.agents/skills/floeva-smart-ring
```

For legacy automatic installations, remove the relevant copies:

```bash
rm -rf ~/.codex/skills/floeva-smart-ring
rm -rf ~/.claude/skills/floeva-smart-ring
rm -rf ~/.openclaw/skills/floeva-smart-ring
rm -rf ~/.floeva  # optional: removes authorization data
```

## License

MIT
