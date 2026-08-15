#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALLED=0
INSTALL_TEMP=""

cleanup() {
  [ -z "$INSTALL_TEMP" ] || rm -f "$INSTALL_TEMP"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$SOURCE_DIR/SKILL.md" ] \
  || [ ! -f "$SOURCE_DIR/scripts/floeva-auth.sh" ] \
  || [ ! -f "$SOURCE_DIR/scripts/floeva-auth.py" ] \
  || [ ! -f "$SOURCE_DIR/references/data-presentation.md" ] \
  || [ ! -f "$SOURCE_DIR/agents/openai.yaml" ]; then
  printf '%s\n' "Run install.sh from a complete floeva-smart-ring-skill checkout." >&2
  exit 1
fi

grep -q '^name: floeva-smart-ring$' "$SOURCE_DIR/SKILL.md"
grep -q '^interface:' "$SOURCE_DIR/agents/openai.yaml"
sh -n "$SOURCE_DIR/scripts/floeva-auth.sh"
python3 -c 'compile(open(__import__("sys").argv[1], encoding="utf-8").read(), __import__("sys").argv[1], "exec")' \
  "$SOURCE_DIR/scripts/floeva-auth.py"

install_file() {
  source_file="$1"
  destination="$2"
  file_mode="$3"
  destination_dir=$(dirname -- "$destination")
  mkdir -p "$destination_dir"
  INSTALL_TEMP=$(mktemp "$destination_dir/.floeva-install.XXXXXX")
  cp "$source_file" "$INSTALL_TEMP"
  chmod "$file_mode" "$INSTALL_TEMP"
  mv -f "$INSTALL_TEMP" "$destination"
  INSTALL_TEMP=""
}

install_to() {
  target="$1"
  # Install runtime dependencies first and SKILL.md last. Existing instructions
  # remain usable if an update is interrupted before the final atomic replace.
  install_file "$SOURCE_DIR/scripts/floeva-auth.py" "$target/scripts/floeva-auth.py" 755
  install_file "$SOURCE_DIR/agents/openai.yaml" "$target/agents/openai.yaml" 644
  install_file "$SOURCE_DIR/references/data-presentation.md" "$target/references/data-presentation.md" 644
  install_file "$SOURCE_DIR/scripts/floeva-auth.sh" "$target/scripts/floeva-auth.sh" 755
  install_file "$SOURCE_DIR/SKILL.md" "$target/SKILL.md" 644
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
