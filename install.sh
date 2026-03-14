#!/bin/bash
# Floeva Smart Ring Skill - Auto Installer
# Detects Claude Code and OpenClaw, installs to all available platforms.

set -e

SKILL_URL="https://raw.githubusercontent.com/RogerLuoJian/floeva-smart-ring-skill/main/SKILL.md"
SKILL_FILE="SKILL.md"
INSTALLED=0

# Use local SKILL.md if running from repo directory, otherwise download
if [ -f "$SKILL_FILE" ]; then
  SOURCE="local"
else
  SOURCE="remote"
  echo "Downloading SKILL.md..."
  curl -sSL -o /tmp/floeva-smart-ring-SKILL.md "$SKILL_URL"
  SKILL_FILE="/tmp/floeva-smart-ring-SKILL.md"
fi

# Install to Claude Code
CLAUDE_DIR="$HOME/.claude/skills/floeva-smart-ring"
if [ -d "$HOME/.claude" ]; then
  mkdir -p "$CLAUDE_DIR"
  cp "$SKILL_FILE" "$CLAUDE_DIR/SKILL.md"
  echo "[OK] Installed to Claude Code: $CLAUDE_DIR"
  INSTALLED=$((INSTALLED + 1))
fi

# Install to OpenClaw
OPENCLAW_DIR="$HOME/.openclaw/skills/floeva-smart-ring"
if [ -d "$HOME/.openclaw" ]; then
  mkdir -p "$OPENCLAW_DIR"
  cp "$SKILL_FILE" "$OPENCLAW_DIR/SKILL.md"
  echo "[OK] Installed to OpenClaw: $OPENCLAW_DIR"
  INSTALLED=$((INSTALLED + 1))
fi

# Cleanup temp file
if [ "$SOURCE" = "remote" ] && [ -f /tmp/floeva-smart-ring-SKILL.md ]; then
  rm /tmp/floeva-smart-ring-SKILL.md
fi

if [ $INSTALLED -eq 0 ]; then
  echo "No supported AI agent platform found (~/.claude or ~/.openclaw)."
  echo ""
  echo "Manual install:"
  echo "  Claude Code: mkdir -p ~/.claude/skills/floeva-smart-ring && cp SKILL.md ~/.claude/skills/floeva-smart-ring/"
  echo "  OpenClaw:    mkdir -p ~/.openclaw/skills/floeva-smart-ring && cp SKILL.md ~/.openclaw/skills/floeva-smart-ring/"
  exit 1
fi

echo ""
echo "Done! Start a new AI session and ask: \"Show my health overview\""
