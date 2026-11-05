#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALLED=0
INSTALL_TEMP=""
EXPLICIT_TARGET=0
TARGET_DIR=""

usage() {
  cat <<'USAGE'
Usage: ./install.sh [--target <skill-directory>]

Install the complete Floeva Skill into any Agent's skill directory:
  ./install.sh --target "$HOME/.agents/skills/floeva-smart-ring"
  ./install.sh --target "$HOME/.hermes/skills/floeva-smart-ring"

--target is the complete destination directory, including the skill folder name.
Explicit installation writes only to that destination. Relative paths are allowed.
Without options, install into existing Codex, Claude Code and OpenClaw directories;
if none exist, use ~/.agents/skills/floeva-smart-ring. The Agent must be configured
to discover the chosen directory and be able to run Bash and Python 3.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      if [ "$EXPLICIT_TARGET" -eq 1 ] || [ "$#" -lt 2 ] || [ -z "$2" ]; then
        printf '%s\n' 'Provide --target exactly once with a nonempty skill directory.' >&2
        exit 1
      fi
      case "$2" in
        -*) printf '%s\n' 'Invalid target directory; use an absolute path or ./relative-path.' >&2; exit 1 ;;
      esac
      EXPLICIT_TARGET=1
      TARGET_DIR="$2"
      shift 2
      ;;
    --help|-h)
      if [ "$#" -ne 1 ] || [ "$EXPLICIT_TARGET" -eq 1 ]; then
        printf '%s\n' 'Use --help on its own.' >&2
        exit 1
      fi
      usage
      exit 0
      ;;
    *)
      printf '%s\n' "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

cleanup() {
  [ -z "$INSTALL_TEMP" ] || rm -f "$INSTALL_TEMP"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$SOURCE_DIR/SKILL.md" ] \
  || [ ! -f "$SOURCE_DIR/scripts/floeva-auth.sh" ] \
  || [ ! -f "$SOURCE_DIR/scripts/floeva-auth.py" ] \
  || [ ! -f "$SOURCE_DIR/scripts/floeva-report.py" ] \
  || [ ! -f "$SOURCE_DIR/references/data-presentation.md" ] \
  || [ ! -f "$SOURCE_DIR/references/health-canvas.md" ] \
  || [ ! -f "$SOURCE_DIR/assets/health-report/index.html" ] \
  || [ ! -f "$SOURCE_DIR/assets/health-report/app.css" ] \
  || [ ! -f "$SOURCE_DIR/assets/health-report/app.js" ] \
  || [ ! -f "$SOURCE_DIR/agents/openai.yaml" ]; then
  printf '%s\n' "Run install.sh from a complete floeva-smart-ring-skill checkout." >&2
  exit 1
fi

grep -q '^name: floeva-smart-ring$' "$SOURCE_DIR/SKILL.md"
grep -q '^interface:' "$SOURCE_DIR/agents/openai.yaml"
sh -n "$SOURCE_DIR/scripts/floeva-auth.sh"
python3 -c 'compile(open(__import__("sys").argv[1], encoding="utf-8").read(), __import__("sys").argv[1], "exec")' \
  "$SOURCE_DIR/scripts/floeva-auth.py"
python3 -c 'compile(open(__import__("sys").argv[1], encoding="utf-8").read(), __import__("sys").argv[1], "exec")' \
  "$SOURCE_DIR/scripts/floeva-report.py"
grep -q 'Floeva Health Canvas' "$SOURCE_DIR/assets/health-report/index.html"
grep -q 'fetch("./report.json"' "$SOURCE_DIR/assets/health-report/app.js"
python3 -c 'import sys; assert all(open(path, "rb").read(4) in (b"OTTO", b"\x00\x01\x00\x00") for path in sys.argv[1:])' \
  "$SOURCE_DIR/assets/health-report/fonts/Inter-Regular.ttf" \
  "$SOURCE_DIR/assets/health-report/fonts/Inter-Bold.ttf"

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
  install_file "$SOURCE_DIR/scripts/floeva-report.py" "$target/scripts/floeva-report.py" 755
  install_file "$SOURCE_DIR/agents/openai.yaml" "$target/agents/openai.yaml" 644
  install_file "$SOURCE_DIR/references/data-presentation.md" "$target/references/data-presentation.md" 644
  install_file "$SOURCE_DIR/references/health-canvas.md" "$target/references/health-canvas.md" 644
  install_file "$SOURCE_DIR/assets/health-report/index.html" "$target/assets/health-report/index.html" 644
  install_file "$SOURCE_DIR/assets/health-report/app.css" "$target/assets/health-report/app.css" 644
  install_file "$SOURCE_DIR/assets/health-report/app.js" "$target/assets/health-report/app.js" 644
  install_file "$SOURCE_DIR/assets/health-report/logo-icon.svg" "$target/assets/health-report/logo-icon.svg" 644
  install_file "$SOURCE_DIR/assets/health-report/lotus.svg" "$target/assets/health-report/lotus.svg" 644
  install_file "$SOURCE_DIR/assets/health-report/fonts/Inter-Regular.ttf" "$target/assets/health-report/fonts/Inter-Regular.ttf" 644
  install_file "$SOURCE_DIR/assets/health-report/fonts/Inter-Bold.ttf" "$target/assets/health-report/fonts/Inter-Bold.ttf" 644
  install_file "$SOURCE_DIR/scripts/floeva-auth.sh" "$target/scripts/floeva-auth.sh" 755
  install_file "$SOURCE_DIR/SKILL.md" "$target/SKILL.md" 644
  printf '%s\n' "[OK] Installed: $target"
  INSTALLED=$((INSTALLED + 1))
}

if [ "$EXPLICIT_TARGET" -eq 1 ]; then
  install_to "$TARGET_DIR"
else
  # Compatibility shortcuts, not a registry of supported Agent products.
  [ ! -d "$HOME/.codex" ] || install_to "$HOME/.codex/skills/floeva-smart-ring"
  [ ! -d "$HOME/.claude" ] || install_to "$HOME/.claude/skills/floeva-smart-ring"
  [ ! -d "$HOME/.openclaw" ] || install_to "$HOME/.openclaw/skills/floeva-smart-ring"
  if [ "$INSTALLED" -eq 0 ]; then
    install_to "$HOME/.agents/skills/floeva-smart-ring"
  fi
fi

printf '%s\n' "Files installed. Enable discovery of this directory in your Agent, then start a new session and ask: Show my Floeva health overview as a visual report."
