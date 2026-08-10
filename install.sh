#!/bin/sh
set -eu

REPO_RAW="https://raw.githubusercontent.com/RogerLuoJian/floeva-smart-ring-skill/main"
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEMP_DIR=""
INSTALLED=0

cleanup() {
  [ -z "$TEMP_DIR" ] || rm -rf "$TEMP_DIR"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$SOURCE_DIR/SKILL.md" ] || [ ! -f "$SOURCE_DIR/scripts/floeva-auth.sh" ]; then
  TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/floeva-skill.XXXXXX")
  mkdir -p "$TEMP_DIR/scripts"
  curl -sSLo "$TEMP_DIR/SKILL.md" "$REPO_RAW/SKILL.md"
  curl -sSLo "$TEMP_DIR/scripts/floeva-auth.sh" "$REPO_RAW/scripts/floeva-auth.sh"
  SOURCE_DIR="$TEMP_DIR"
fi

install_to() {
  target="$1"
  mkdir -p "$target/scripts"
  cp "$SOURCE_DIR/SKILL.md" "$target/SKILL.md"
  cp "$SOURCE_DIR/scripts/floeva-auth.sh" "$target/scripts/floeva-auth.sh"
  chmod 755 "$target/scripts/floeva-auth.sh"
  printf '%s\n' "[OK] Installed: $target"
  INSTALLED=$((INSTALLED + 1))
}

[ ! -d "$HOME/.codex" ] || install_to "$HOME/.codex/skills/floeva-smart-ring"
[ ! -d "$HOME/.claude" ] || install_to "$HOME/.claude/skills/floeva-smart-ring"
[ ! -d "$HOME/.openclaw" ] || install_to "$HOME/.openclaw/skills/floeva-smart-ring"

if [ "$INSTALLED" -eq 0 ]; then
  printf '%s\n' "No supported Agent directory found (~/.codex, ~/.claude, or ~/.openclaw)." >&2
  exit 1
fi

printf '%s\n' "Done. Start a new Agent session and ask: Show my Floeva health overview."
