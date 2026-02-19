#!/usr/bin/env bash
# sync_skill.sh — Sync repo skill to ~/.claude/skills/ and verify identity.
#
# Copies skills/dev-activity-report-skill/ → ~/.claude/skills/dev-activity-report-skill/
# using rsync (excludes runtime/cache files), then runs diff to confirm the
# installed copy is identical to the repo source.
#
# Usage:
#   bash skills/dev-activity-report-skill/scripts/sync_skill.sh
#   bash skills/dev-activity-report-skill/scripts/sync_skill.sh --check-only
#   bash skills/dev-activity-report-skill/scripts/sync_skill.sh --dry-run
#
# Options:
#   --check-only  Diff only, do not sync
#   --dry-run     Show what rsync would do, do not write
#
# Exit codes:
#   0 — sync complete and copies are identical
#   1 — diff found differences (copies diverged)
#   2 — environment/tool error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_BASE="${CLAUDE_SKILLS_DIR:-${HOME}/.claude/skills}"
INSTALL_DIR="${INSTALL_BASE}/dev-activity-report-skill"

CHECK_ONLY=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=1 ;;
    --dry-run)    DRY_RUN=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Files/dirs to exclude from sync (runtime artifacts, caches, and user config)
# .env is excluded from rsync — handled separately below to preserve user values.
RSYNC_EXCLUDES=(
  --exclude=".env"
  --exclude=".phase1-cache.json"
  --exclude=".phase1-cache.tmp"
  --exclude=".dev-report-cache.md"
  --exclude="*.log"
  --exclude="*.pyc"
  --exclude="__pycache__/"
  --exclude="scripts/.phase1-cache.json"
)

echo "sync_skill: repo → installed"
echo "  source : $SKILL_DIR"
echo "  dest   : $INSTALL_DIR"

# ------------------------------------------------------------------
# Step 1 — Sync (unless --check-only)
# ------------------------------------------------------------------
if [[ $CHECK_ONLY -eq 0 ]]; then
  if ! command -v rsync &>/dev/null; then
    echo "ERROR: rsync not found on PATH. Install it or use --check-only." >&2
    exit 2
  fi

  mkdir -p "$INSTALL_DIR"

  RSYNC_FLAGS=(-av --delete)
  [[ $DRY_RUN -eq 1 ]] && RSYNC_FLAGS+=(--dry-run)

  echo ""
  echo "[1/2] Syncing..."
  rsync "${RSYNC_FLAGS[@]}" "${RSYNC_EXCLUDES[@]}" "$SKILL_DIR/" "$INSTALL_DIR/"

  if [[ $DRY_RUN -eq 1 ]]; then
    echo ""
    echo "sync_skill: dry-run complete (no files written)"
    exit 0
  fi
  echo "  OK sync done"

  # ----------------------------------------------------------------
  # .env — merge new keys from .env.example; never overwrite values.
  # ----------------------------------------------------------------
  INSTALLED_ENV="$INSTALL_DIR/.env"
  EXAMPLE_ENV="$SKILL_DIR/references/examples/.env.example"

  if [[ ! -f "$INSTALLED_ENV" ]]; then
    if [[ -f "$EXAMPLE_ENV" ]]; then
      cp "$EXAMPLE_ENV" "$INSTALLED_ENV"
      echo "  .env created from .env.example at $INSTALLED_ENV"
    else
      echo "  (no .env.example found; skipping .env creation)"
    fi
  else
    # Add keys from .env.example that are missing in the installed .env.
    if [[ -f "$EXAMPLE_ENV" ]]; then
      added=0
      while IFS= read -r line; do
        # Skip blank lines and comments
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        key="${line%%=*}"
        [[ -z "$key" ]] && continue
        # Only add if key is entirely absent from the installed .env
        if ! grep -q "^${key}=" "$INSTALLED_ENV" 2>/dev/null; then
          echo "$line" >> "$INSTALLED_ENV"
          echo "  .env: added new key: $key"
          added=$((added + 1))
        fi
      done < "$EXAMPLE_ENV"
      if [[ $added -eq 0 ]]; then
        echo "  No .env changes needed at $INSTALLED_ENV."
      fi
    fi
  fi
else
  echo "  (--check-only: skipping rsync)"
fi

# ------------------------------------------------------------------
# Step 2 — Verify identity with diff
# ------------------------------------------------------------------
echo ""
echo "[2/2] Verifying copies are identical..."

if [[ ! -d "$INSTALL_DIR" ]]; then
  echo "ERROR: install dir does not exist: $INSTALL_DIR" >&2
  echo "  Run without --check-only to sync first." >&2
  exit 2
fi

# Build exclude args for diff (same exclusion list; .env excluded — user config may differ)
DIFF_EXCLUDES=(
  --exclude=".env"
  --exclude=".phase1-cache.json"
  --exclude=".phase1-cache.tmp"
  --exclude=".dev-report-cache.md"
  --exclude="*.log"
  --exclude="*.pyc"
  --exclude="__pycache__"
)

diff_output="$(diff -rq "${DIFF_EXCLUDES[@]}" "$SKILL_DIR" "$INSTALL_DIR" 2>&1 || true)"

if [[ -z "$diff_output" ]]; then
  echo "  OK copies are identical"
  echo ""
  echo "sync_skill: SUCCESS"
  exit 0
else
  echo "  DIFF FOUND:"
  echo "$diff_output" | sed 's/^/    /'
  echo ""
  echo "sync_skill: FAIL — installed copy differs from repo source" >&2
  echo "  Run without --check-only to re-sync." >&2
  exit 1
fi
