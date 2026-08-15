# Floeva Smart Ring Skill

An official Agent skill for securely connecting to [Floeva](https://getfloeva.com) smart-ring health data.

## What it does

- Opens a Floeva-owned webpage for authorization—no API key copy/paste
- Reads health overviews, sleep, heart rate, HRV, steps, and Flow score
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

The installer must run from a complete repository checkout; it does not execute or assemble runtime files from a mutable remote branch. It detects Codex, Claude Code, and OpenClaw, validates the checked-out files, and installs the skill instructions, UI metadata, and web-authorization helper.

## Use

Start a new Agent session and ask naturally:

- “Show my Floeva health overview.”
- “How did I sleep last night?”
- “What is my heart-rate trend?”
- “How do I charge my Floeva ring?”

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

## Uninstall

```bash
rm -rf ~/.codex/skills/floeva-smart-ring
rm -rf ~/.claude/skills/floeva-smart-ring
rm -rf ~/.openclaw/skills/floeva-smart-ring
rm -rf ~/.floeva  # optional: removes authorization data
```

## License

MIT
