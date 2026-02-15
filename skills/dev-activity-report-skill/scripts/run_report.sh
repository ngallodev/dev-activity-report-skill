#!/usr/bin/env bash
set -euo pipefail

# Background-first runner for dev-activity-report.
# Default: background run with no terminal output; sends notification on completion.
# Foreground: pass --foreground to stream output.

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

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
REPORT_SANDBOX="${REPORT_SANDBOX:-workspace-write}"

# Output directory: prefer REPORT_OUTPUT_DIR from .env, fall back to $HOME.
OUTPUT_DIR="${REPORT_OUTPUT_DIR:-$HOME}"
OUTPUT_DIR="${OUTPUT_DIR/#\~/$HOME}"  # expand leading ~ if literal

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

  # No notification tool found; print a hint and continue without hard-failing.
  echo "dev-activity-report: $message" >&2
  echo "(Install libnotify-bin (Linux: sudo apt-get install libnotify-bin) or terminal-notifier (macOS: brew install terminal-notifier) for desktop notifications.)" >&2
}

if [[ ! -d "$OUTPUT_DIR" ]]; then
  echo "Output directory does not exist: $OUTPUT_DIR" >&2
  echo "Create it or set REPORT_OUTPUT_DIR to an existing directory in .env." >&2
  exit 1
fi
if [[ ! -w "$OUTPUT_DIR" ]]; then
  echo "Output directory is not writable: $OUTPUT_DIR" >&2
  echo "Choose a writable REPORT_OUTPUT_DIR in .env." >&2
  exit 1
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$OUTPUT_DIR/codex-run-$TS.log"
PHASE15_OUT="$OUTPUT_DIR/codex-phase1_5-last-message.txt"
PHASE2_OUT="$OUTPUT_DIR/codex-phase2-last-message.txt"
REPORT_OUT="$OUTPUT_DIR/codex-test-report-$TS.md"

FOREGROUND=false
if [[ "${1:-}" == "--foreground" ]]; then
  FOREGROUND=true
fi

if [[ "$FOREGROUND" == "false" ]]; then
  nohup "$0" --foreground >"$LOG_FILE" 2>&1 &
  exit 0
fi

CODEX_BIN="${CODEX_BIN:-$(command -v codex 2>/dev/null || true)}"
if [[ -z "$CODEX_BIN" ]]; then
  echo "codex binary not found on PATH. Install it and ensure it is executable." >&2
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

WORKSPACE_DIR="$(pwd -P)"
python3 - "$WORKSPACE_DIR" "$APPS_DIR" "$EXTRA_SCAN_DIRS" "$OUTPUT_DIR" "$PHASE1_MODEL" "$PHASE15_MODEL" "$PHASE2_MODEL" "$PHASE3_MODEL" "$REPORT_SANDBOX" <<'PY'
import os
import sys
from pathlib import Path

workspace = Path(sys.argv[1]).resolve()
apps_dir = sys.argv[2]
extra_dirs_raw = sys.argv[3]
output_dir = sys.argv[4]
models = sys.argv[5:9]
sandbox = sys.argv[9]

def is_claude_model(name: str) -> bool:
    return "claude" in (name or "").lower()

def split_paths(raw: str) -> list[str]:
    if not raw:
        return []
    parts = []
    for chunk in raw.replace(",", " ").replace(":", " ").split():
        parts.append(chunk)
    return parts

paths = [apps_dir, output_dir]
paths.extend(split_paths(extra_dirs_raw))

outside = []
for p in paths:
    try:
        rp = Path(os.path.expanduser(p)).resolve()
    except Exception:
        continue
    if workspace not in rp.parents and rp != workspace:
        outside.append(str(rp))

if outside and any(not is_claude_model(m) for m in models):
    sys.stderr.write("Warning: non-Claude model in use while paths are outside the Codex workspace.\n")
    sys.stderr.write(f"Workspace: {workspace}\n")
    for item in outside:
        sys.stderr.write(f"Outside path: {item}\n")
    sys.stderr.write("Consider running from a workspace that contains those paths or keep REPORT_SANDBOX at workspace-write for safety.\n")

if outside and sandbox == "workspace-write":
    sys.stderr.write("Error: REPORT_SANDBOX=workspace-write but some paths are outside the workspace.\n")
    sys.exit(2)
PY
if [[ $? -eq 2 ]]; then
  echo "Blocking run because workspace-write cannot access required paths." >&2
  echo "Either run from a workspace that contains those paths or set REPORT_SANDBOX to a more permissive mode." >&2
  exit 1
fi
  true
fi

echo "== Phase 1 ($PHASE1_MODEL): data gathering =="
"$CODEX_BIN" exec -m "$PHASE1_MODEL" --approval never --sandbox "$REPORT_SANDBOX" - <<EOF
Please run \`python3 "$SKILL_DIR/scripts/phase1_runner.py"\` and print only the JSON output produced by the script.
EOF

echo "== Phase 1.5 ($PHASE15_MODEL): draft =="
"$CODEX_BIN" exec -m "$PHASE15_MODEL" --approval never --sandbox "$REPORT_SANDBOX" --output-last-message "$PHASE15_OUT" - <<EOF
Use advanced reasoning. Read the JSON blob at $SKILL_DIR/.phase1-cache.json.
Output a rough draft only: 5–8 bullets + a 2-sentence overview. No extra commentary.
EOF

echo "== Phase 2 ($PHASE2_MODEL): report =="
"$CODEX_BIN" exec -m "$PHASE2_MODEL" --approval never --sandbox "$REPORT_SANDBOX" --output-last-message "$PHASE2_OUT" - <<EOF
You are a senior resume/portfolio writer with excellent creative writing and deep technical understanding. Read the JSON blob stored at $SKILL_DIR/.phase1-cache.json and the draft at $PHASE15_OUT, then produce:

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
"$CODEX_BIN" exec -m "$PHASE3_MODEL" --approval never --sandbox "$REPORT_SANDBOX" - <<EOF
Please run the following Python command:

python3 - <<'PY'
import json
from pathlib import Path

skill_dir = Path("$SKILL_DIR")
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
