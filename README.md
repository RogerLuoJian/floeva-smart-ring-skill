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

The installer detects Codex, Claude Code, and OpenClaw and copies both the skill instructions and the web-authorization helper.

## Use

Start a new Agent session and ask naturally:

- “Show my Floeva health overview.”
- “How did I sleep last night?”
- “What is my heart-rate trend?”
- “How do I charge my Floeva ring?”

On first use, the Agent asks whether you use Floeva Global or China, then gives you a short-lived Floeva website link and matching code. Sign in on that page, approve, and return to the Agent.

Authorization is stored in `~/.floeva/config.json` with file mode `0600`. The access token is time-limited and can be replaced by authorizing again. Existing legacy `api_key` configs remain supported during migration.

## Uninstall

```bash
rm -rf ~/.codex/skills/floeva-smart-ring
rm -rf ~/.claude/skills/floeva-smart-ring
rm -rf ~/.openclaw/skills/floeva-smart-ring
rm -rf ~/.floeva  # optional: removes authorization data
```

## License

MIT
