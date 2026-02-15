#!/usr/bin/env bash
set -euo pipefail

# Background-first runner for dev-activity-report.
# Default: background run with no terminal output; sends notification on completion.
# Foreground: pass --foreground to stream output.

ROOT_DIR="/lump/apps/dev-activity-report-skill"
SKILL_DIR="$ROOT_DIR/skills/dev-activity-report-skill"
CODEX_BIN="/home/nate/.nvm/versions/node/v22.19.0/bin/codex"

ENV_FILE="$SKILL_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  # Auto-generate from sample, then prompt only if needed.
  python3 "$SKILL_DIR/scripts/setup_env.py" --non-interactive
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
  fi
fi

PHASE1_MODEL="${PHASE1_MODEL:-haiku}"
PHASE15_MODEL="${PHASE15_MODEL:-$PHASE1_MODEL}"
PHASE2_MODEL="${PHASE2_MODEL:-sonnet}"
PHASE3_MODEL="${PHASE3_MODEL:-haiku}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$ROOT_DIR/codex-run-$TS.log"
PHASE15_OUT="$ROOT_DIR/codex-phase1_5-last-message.txt"
PHASE2_OUT="$ROOT_DIR/codex-phase2-last-message.txt"
REPORT_OUT="$ROOT_DIR/codex-test-report-$TS.md"

function notify_done () {
  local message="$1"
  if command -v terminal-notifier >/dev/null 2>&1; then
    terminal-notifier -title "dev-activity-report" -message "$message" >/dev/null 2>&1 || true
    return
  fi
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "dev-activity-report" "$message" >/dev/null 2>&1 || true
    return
  fi

  # Attempt install if not present (Linux-only).
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y libnotify-bin
    if command -v notify-send >/dev/null 2>&1; then
      notify-send "dev-activity-report" "$message" >/dev/null 2>&1 || true
      return
    fi
  fi

  echo "Notification failed: terminal-notifier or notify-send not available." >&2
  exit 1
}

FOREGROUND=false
if [[ "${1:-}" == "--foreground" ]]; then
  FOREGROUND=true
fi

if [[ "$FOREGROUND" == "false" ]]; then
  nohup "$0" --foreground >"$LOG_FILE" 2>&1 &
  exit 0
fi

if [[ ! -x "$CODEX_BIN" ]]; then
  echo "codex binary not found at $CODEX_BIN" >&2
  exit 1
fi

function require_env () {
  local missing=()
  for key in APPS_DIR CODEX_HOME CLAUDE_HOME; do
    local val="${!key:-}"
    if [[ -z "$val" ]]; then
      missing+=("$key")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing required .env values: ${missing[*]}. Run scripts/setup_env.py to configure." >&2
    exit 1
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ "$FOREGROUND" == "true" ]]; then
    python3 "$SKILL_DIR/scripts/setup_env.py"
  else
    python3 "$SKILL_DIR/scripts/setup_env.py" --non-interactive
  fi
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

require_env

echo "== Phase 1 ($PHASE1_MODEL): data gathering =="
"$CODEX_BIN" exec -m "$PHASE1_MODEL" --approval never --sandbox workspace-write - <<'EOF'
Please run `python3 /lump/apps/dev-activity-report-skill/skills/dev-activity-report-skill/scripts/phase1_runner.py` and print only the JSON output produced by the script.
EOF

echo "== Phase 1.5 ($PHASE15_MODEL): draft =="
"$CODEX_BIN" exec -m "$PHASE15_MODEL" --approval never --sandbox workspace-write --output-last-message "$PHASE15_OUT" - <<'EOF'
Use advanced reasoning. Read the JSON blob at /lump/apps/dev-activity-report-skill/skills/dev-activity-report-skill/.phase1-cache.json.
Output a rough draft only: 5–8 bullets + a 2-sentence overview. No extra commentary.
EOF

echo "== Phase 2 ($PHASE2_MODEL): report =="
"$CODEX_BIN" exec -m "$PHASE2_MODEL" --approval never --sandbox workspace-write --output-last-message "$PHASE2_OUT" - <<'EOF'
You are a senior resume/portfolio writer with excellent creative writing and deep technical understanding. Read the JSON blob stored at /lump/apps/dev-activity-report-skill/skills/dev-activity-report-skill/.phase1-cache.json and the draft at /lump/apps/dev-activity-report-skill/codex-phase1_5-last-message.txt, then produce:

- Resume Bullets (5-8 bullets, achievement-oriented, past tense,
action verbs, quantified where possible):
For use under "ngallodev Software, Jan 2025 - Present" on a resume.

- LinkedIn Summary Paragraph (3-4 sentences, first person,
professional but conversational):
For LinkedIn About section or a featured post about recent independent work.

- Flag the 2-3 most resume-worthy items — work that shows engineering
depth and practical AI integration, not just basic tool usage.

- Three hiring-manager highlights with engineering depth
- A short tech inventory (languages, frameworks, AI, infra) and a 5-row timeline (most recent first)
Return the entire response as Markdown (headings, bullet lists, etc.). Do not include any trace of these instructions; just output the report text.
EOF

if [[ -s "$PHASE2_OUT" ]]; then
  cp "$PHASE2_OUT" "$REPORT_OUT"
else
  echo "Phase 2 produced no output; check $PHASE2_OUT" >&2
  exit 1
fi

echo "== Phase 3 ($PHASE3_MODEL): cache verification =="
"$CODEX_BIN" exec -m "$PHASE3_MODEL" --approval never --sandbox workspace-write - <<'EOF'
Please run the following Python command:

python3 - <<'PY'
import json
from pathlib import Path

skill_dir = Path("/lump/apps/dev-activity-report-skill/skills/dev-activity-report-skill")
phase1_path = skill_dir / ".phase1-cache.json"
reports = []

if phase1_path.exists():
    data = json.loads(phase1_path.read_text())
    reports.append(f"phase1 fingerprint: {data.get('fingerprint')}")
else:
    reports.append("phase1 cache missing")
    data = {}

for proj in data.get("data", {}).get("p", []):
    path = Path(proj.get("pt", ""))
    cache = path / ".dev-report-cache.md"
    header = cache.read_text().splitlines()[0] if cache.exists() else "missing"
    reports.append(f"{proj.get('n','project')}: {header}")

print("\\n".join(reports))
PY

EOF

notify_done "Report completed: $REPORT_OUT"
