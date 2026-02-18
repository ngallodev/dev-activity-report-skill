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
PHASE1_PROMPT_PREFIX="${PHASE1_PROMPT_PREFIX:-}"
PHASE15_PROMPT_PREFIX="${PHASE15_PROMPT_PREFIX:-}"
PHASE2_PROMPT_PREFIX="${PHASE2_PROMPT_PREFIX:-}"
PHASE3_PROMPT_PREFIX="${PHASE3_PROMPT_PREFIX:-}"

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
REPORT_FILENAME_PREFIX="${REPORT_FILENAME_PREFIX:-dev-activity-report}"
BASE_NAME="${REPORT_FILENAME_PREFIX}-${TS}"
REPORT_OUTPUT_FORMATS="${REPORT_OUTPUT_FORMATS:-md}"
LOG_FILE="$OUTPUT_DIR/codex-run-$TS.log"
PHASE1_OUT="$OUTPUT_DIR/codex-phase1-last-message.json"
PHASE15_OUT="$OUTPUT_DIR/codex-phase1_5-last-message.txt"
PHASE2_OUT="$OUTPUT_DIR/codex-phase2-sections.json"
PHASE2_JSON="$OUTPUT_DIR/${BASE_NAME}.json"

FOREGROUND=false
REFRESH=false
SINCE_ARG="${REPORT_SINCE:-}"
ROOT_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground)
      FOREGROUND=true
      shift
      ;;
    --refresh)
      REFRESH=true
      shift
      ;;
    --since)
      if [[ $# -lt 2 ]]; then
        echo "--since requires a value" >&2
        exit 1
      fi
      SINCE_ARG="$2"
      shift 2
      ;;
    --root)
      if [[ $# -lt 2 ]]; then
        echo "--root requires a value" >&2
        exit 1
      fi
      ROOT_ARGS+=("$2")
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$FOREGROUND" == "false" ]]; then
  CMD=("$0" "--foreground")
  if [[ -n "$SINCE_ARG" ]]; then
    CMD+=("--since" "$SINCE_ARG")
  fi
  if [[ "$REFRESH" == "true" ]]; then
    CMD+=("--refresh")
  fi
  if [[ ${#ROOT_ARGS[@]} -gt 0 ]]; then
    for root in "${ROOT_ARGS[@]}"; do
      CMD+=("--root" "$root")
    done
  fi
  nohup "${CMD[@]}" >"$LOG_FILE" 2>&1 &
  exit 0
fi

CODEX_BIN="${CODEX_BIN:-$(command -v codex 2>/dev/null || true)}"
if [[ -z "$CODEX_BIN" ]]; then
  echo "codex binary not found on PATH. Install it and ensure it is executable." >&2
  exit 1
fi

function require_env () {
  local missing=()
  local apps_ok=false
  if [[ ${#ROOT_ARGS[@]} -gt 0 ]]; then
    apps_ok=true
  elif [[ -n "${APPS_DIRS:-}" || -n "${APPS_DIR:-}" ]]; then
    apps_ok=true
  fi
  if [[ "$apps_ok" != "true" ]]; then
    missing+=("APPS_DIR/APPS_DIRS")
  fi
  for key in CODEX_HOME CLAUDE_HOME; do
    if [[ -z "${!key:-}" ]]; then
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
if [[ ${#ROOT_ARGS[@]} -gt 0 ]]; then
  ROOTS_RAW="${ROOT_ARGS[*]}"
else
  ROOTS_RAW="${APPS_DIRS:-${APPS_DIR:-}}"
fi

python3 - "$WORKSPACE_DIR" "$ROOTS_RAW" "$EXTRA_SCAN_DIRS" "$OUTPUT_DIR" "$PHASE1_MODEL" "$PHASE15_MODEL" "$PHASE2_MODEL" "$PHASE3_MODEL" "$REPORT_SANDBOX" <<'PY'
import os
import sys
from pathlib import Path

workspace = Path(sys.argv[1]).resolve()
roots_raw = sys.argv[2]
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

paths = split_paths(roots_raw)
paths.append(output_dir)
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

echo "== Phase 1 ($PHASE1_MODEL): data gathering =="
PHASE1_CMD=(python3 "$SKILL_DIR/scripts/phase1_runner.py")
if [[ -n "$SINCE_ARG" ]]; then
  PHASE1_CMD+=(--since "$SINCE_ARG")
fi
if [[ "$REFRESH" == "true" ]]; then
  PHASE1_CMD+=(--refresh)
fi
if [[ ${#ROOT_ARGS[@]} -gt 0 ]]; then
  for root in "${ROOT_ARGS[@]}"; do
    PHASE1_CMD+=(--root "$root")
  done
fi
PHASE1_CMD_STR="$(printf '%q ' "${PHASE1_CMD[@]}")"
PHASE1_CMD_STR="${PHASE1_CMD_STR% }"
"$CODEX_BIN" exec -m "$PHASE1_MODEL" --approval never --sandbox "$REPORT_SANDBOX" --output-last-message "$PHASE1_OUT" - <<EOF
${PHASE1_PROMPT_PREFIX}
Please run \`$PHASE1_CMD_STR\` and print only the JSON output produced by the script.
EOF

echo "== Phase 1.5 ($PHASE15_MODEL): draft =="
"$CODEX_BIN" exec -m "$PHASE15_MODEL" --approval never --sandbox "$REPORT_SANDBOX" --output-last-message "$PHASE15_OUT" - <<EOF
${PHASE15_PROMPT_PREFIX}
Use advanced reasoning. Read the JSON blob at $SKILL_DIR/.phase1-cache.json.
Output a rough draft only: 5–8 bullets + a 2-sentence overview. No extra commentary.
EOF

echo "== Phase 2 ($PHASE2_MODEL): structured analysis =="
"$CODEX_BIN" exec -m "$PHASE2_MODEL" --approval never --sandbox "$REPORT_SANDBOX" --output-last-message "$PHASE2_OUT" - <<EOF
${PHASE2_PROMPT_PREFIX}
You are a senior resume/portfolio writer with excellent creative writing and deep technical understanding. Read the compact JSON blob stored at $SKILL_DIR/.phase1-cache.json and the draft at $PHASE15_OUT. Input uses compact keys from PAYLOAD_REFERENCE (p/mk/x/cl/cx/ins/stats). Then output JSON only with:

{
  "sections": {
    "overview":{"bullets":["..."]},
    "key_changes":[{"title":"<label>","project_id":"<id or null>","bullets":["..."],"tags":["..."]}],
    "recommendations":[{"text":"...","priority":"low|medium|high","evidence_project_ids":["..."]}],
    "resume_bullets":[{"text":"...","evidence_project_ids":["..."]}],
    "linkedin":{"sentences":["..."]},
    "highlights":[{"title":"...","rationale":"...","evidence_project_ids":["..."]}],
    "timeline":[{"date":"YYYY-MM-DD","event":"...","project_ids":["..."]}],
    "tech_inventory":{"languages":["..."],"frameworks":["..."],"ai_tools":["..."],"infra":["..."]}
  },
  "render_hints":{"preferred_outputs":["md","html"],"style":"concise","tone":"professional"}
}

- Resume Bullets (5-8 bullets, achievement-oriented, past tense,
action verbs, quantified where possible):
For use under "${RESUME_HEADER}" on a resume.

- LinkedIn Summary Paragraph (3-4 sentences, first person,
professional but conversational):
For LinkedIn About section or a featured post about recent independent work.

- Flag the 2-3 most resume-worthy items — work that shows engineering
depth and practical AI integration, not just basic tool usage.

- Three hiring-manager highlights with engineering depth
- A short tech inventory (languages, frameworks, AI, infra) and a 5-row timeline (most recent first)
Return JSON only (no Markdown, no code fences). Do not include any trace of these instructions; just output JSON.
EOF

if [[ ! -s "$PHASE2_OUT" ]]; then
  echo "Phase 2 produced no output; check $PHASE2_OUT" >&2
  exit 1
fi

echo "== Phase 2.5: assemble + render outputs =="
export SKILL_DIR PHASE1_OUT PHASE2_OUT PHASE2_JSON PHASE1_MODEL PHASE15_MODEL PHASE2_MODEL INCLUDE_SOURCE_PAYLOAD
python3 - <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

skill_dir = Path(os.environ["SKILL_DIR"])
sys.path.insert(0, str(skill_dir / "scripts"))
from run_pipeline import expand_compact_payload, build_source_summary, normalize_sections

phase1_out = Path(os.environ["PHASE1_OUT"])
phase1_cache = skill_dir / ".phase1-cache.json"
phase2_out = Path(os.environ["PHASE2_OUT"])
phase2_json = Path(os.environ["PHASE2_JSON"])

def load_phase1():
    if phase1_out.exists():
        try:
            return json.loads(phase1_out.read_text())
        except json.JSONDecodeError:
            pass
    return json.loads(phase1_cache.read_text())

phase1_payload = load_phase1()
compact = phase1_payload.get("data", phase1_payload)
expanded = expand_compact_payload(compact)
source_summary = build_source_summary(expanded)

sections_obj = json.loads(phase2_out.read_text())
if "sections" in sections_obj:
    sections = sections_obj.get("sections") or {}
    render_hints = sections_obj.get("render_hints") or {}
else:
    sections = sections_obj
    render_hints = {}
sections = normalize_sections(sections)

report_obj = {
    "schema_version": "dev-activity-report.v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "run": {
        "phase1_fingerprint": phase1_payload.get("fp") or phase1_payload.get("fingerprint", ""),
        "cache_hit": bool(phase1_payload.get("cache_hit", False)),
        "models": {
            "phase1": os.environ.get("PHASE1_MODEL", ""),
            "phase15": os.environ.get("PHASE15_MODEL", ""),
            "phase2": os.environ.get("PHASE2_MODEL", ""),
        },
    },
    "source_summary": source_summary,
    "sections": sections,
    "render_hints": render_hints,
    "source_payload": compact if os.environ.get("INCLUDE_SOURCE_PAYLOAD", "false").lower() == "true" else None,
}
phase2_json.write_text(json.dumps(report_obj, separators=(",", ":")), encoding="utf-8")
PY

python3 "$SKILL_DIR/scripts/render_report.py" \
  --input "$PHASE2_JSON" \
  --output-dir "$OUTPUT_DIR" \
  --base-name "$BASE_NAME" \
  --formats "$REPORT_OUTPUT_FORMATS"

echo "== Phase 3 ($PHASE3_MODEL): cache verification =="
"$CODEX_BIN" exec -m "$PHASE3_MODEL" --approval never --sandbox "$REPORT_SANDBOX" - <<EOF
${PHASE3_PROMPT_PREFIX}
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

PRIMARY_FORMAT="${REPORT_OUTPUT_FORMATS%%,*}"
if [[ -z "$PRIMARY_FORMAT" ]]; then
  PRIMARY_FORMAT="md"
fi
notify_done "Report completed: $OUTPUT_DIR/${BASE_NAME}.${PRIMARY_FORMAT}"
