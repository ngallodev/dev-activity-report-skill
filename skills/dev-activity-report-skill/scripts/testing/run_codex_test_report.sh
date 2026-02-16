#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
WORKDIR="$(cd "$SKILL_DIR/../.." && pwd)"
CODEX_BIN="${CODEX_BIN:-$(command -v codex 2>/dev/null || true)}"
PHASE1_MODEL="gpt-5.1-codex-mini"
PHASE15_MODEL="$PHASE1_MODEL"
PHASE2_MODEL="gpt-5.3-codex"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PHASE1_LOG="$WORKDIR/codex-phase1-$TIMESTAMP.log"
PHASE15_TEMP="$WORKDIR/codex-phase1_5-last-message.txt"
PHASE2_TEMP="$WORKDIR/codex-phase2-last-message.txt"
PHASE2_REPORT="$WORKDIR/codex-test-report-$TIMESTAMP.md"
PHASE3_LOG="$WORKDIR/codex-phase3-$TIMESTAMP.log"

function check_codex () {
  if [[ -z "$CODEX_BIN" || ! -x "$CODEX_BIN" ]]; then
    echo "codex binary not found; set CODEX_BIN or ensure codex is on PATH" >&2
    exit 1
  fi
}

check_codex

echo "== Phase 1 ($PHASE1_MODEL): data gathering ==" | tee "$PHASE1_LOG"
"$CODEX_BIN" exec -m "$PHASE1_MODEL" --sandbox workspace-write - <<EOF | tee -a "$PHASE1_LOG"
Please run \`python3 $SKILL_DIR/scripts/phase1_runner.py\` and print only the JSON output produced by the script. After completing, mention the fingerprint stored in $SKILL_DIR/.phase1-cache.json.
EOF

echo
echo "Phase 1 complete. Fingerprint file (if created) is: $SKILL_DIR/.phase1-cache.json"

echo "== Phase 1.5 ($PHASE15_MODEL): draft =="
"$CODEX_BIN" exec -m "$PHASE15_MODEL" --sandbox workspace-write --output-last-message "$PHASE15_TEMP" - <<EOF
Use advanced reasoning. Read the JSON blob at $SKILL_DIR/.phase1-cache.json.
Output a rough draft only: 5–8 bullets + a 2-sentence overview. No extra commentary.
EOF

echo "== Phase 2 ($PHASE2_MODEL): analysis/report =="
"$CODEX_BIN" exec -m "$PHASE2_MODEL" --sandbox workspace-write --output-last-message "$PHASE2_TEMP" - <<EOF
You are a senior resume/portfolio writer with excellent creative writing and deep technical understanding. Read the JSON blob stored at $SKILL_DIR/.phase1-cache.json and the draft at $PHASE15_TEMP, then produce:

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

if [[ -s "$PHASE2_TEMP" ]]; then
  cp "$PHASE2_TEMP" "$PHASE2_REPORT"
  echo "Phase 2 report saved to $PHASE2_REPORT"
else
  echo "Phase 2 produced no output; check $PHASE2_TEMP" >&2
  exit 1
fi

echo "== Phase 3 (gpt-5.1-codex-mini): cache verification =="
"$CODEX_BIN" exec -m gpt-5.1-codex-mini --sandbox workspace-write - <<EOF | tee "$PHASE3_LOG"
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

echo "Phase 3 log: $PHASE3_LOG"
