# Floeva Smart Ring Skill

An AI Agent skill that connects to the [Floeva](https://getfloeva.com) health platform, enabling AI assistants to query your smart ring health data.

Works with **Claude Code**, **OpenClaw**, and other AI Agent platforms that support Markdown-based skills.

## What It Does

- **Health Overview** — Get a summary of your health metrics (sleep, heart rate, steps, Flow score)
- **List Tools** — Discover available health data queries
- **Execute Tools** — Query specific health data (heart rate history, sleep details, HRV, etc.)

## Prerequisites

- A Floeva smart ring (X6 or QRing)
- A Floeva API Key (get one from Floeva App -> Profile -> Account & Security -> API Key)

## Installation

### Claude Code

```bash
mkdir -p ~/.claude/skills/floeva-smart-ring
curl -o ~/.claude/skills/floeva-smart-ring/SKILL.md \
  https://raw.githubusercontent.com/RogerLuoJian/floeva-smart-ring-skill/main/SKILL.md
```

### OpenClaw

```bash
mkdir -p ~/.openclaw/skills/floeva-smart-ring
curl -o ~/.openclaw/skills/floeva-smart-ring/SKILL.md \
  https://raw.githubusercontent.com/RogerLuoJian/floeva-smart-ring-skill/main/SKILL.md
```

### One-Line Install (Auto-Detect)

```bash
curl -sSL https://raw.githubusercontent.com/RogerLuoJian/floeva-smart-ring-skill/main/install.sh | bash
```

## Usage

Once installed, start a new AI session and ask naturally:

- "Show my health overview"
- "How did I sleep last night?"
- "What's my heart rate trend?"
- "What can Floeva do?"

On first use, the AI will guide you through API Key setup. Your key is saved to `~/.floeva/config.json` and shared across all platforms.

## Configuration

API Key and server settings are stored in `~/.floeva/config.json`:

```json
{
  "api_key": "fv_sk_xxx",
  "base_url": "https://us.getfloeva.com/ring/api"
}
```

This file is created automatically on first use with `chmod 600` permissions.

## Security

- API Key stored locally with restricted file permissions (`chmod 600`)
- Key is never hardcoded in commands — always read into shell variables
- Config file is platform-independent, shared across AI agents
- All API calls use HTTPS

## Uninstall

```bash
# Remove from Claude Code
rm -rf ~/.claude/skills/floeva-smart-ring

# Remove from OpenClaw
rm -rf ~/.openclaw/skills/floeva-smart-ring

# Remove config (optional — removes your API Key)
rm -rf ~/.floeva
```

## License

MIT
