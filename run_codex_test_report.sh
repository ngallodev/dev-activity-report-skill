#!/usr/bin/env bash
set -euo pipefail

CODEX_BIN="/home/nate/.nvm/versions/node/v22.19.0/bin/codex"
WORKDIR="/lump/apps/dev-activity-report-skill"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PHASE1_LOG="$WORKDIR/codex-phase1-$TIMESTAMP.log"
PHASE2_TEMP="$WORKDIR/codex-phase2-last-message.txt"
PHASE2_REPORT="$WORKDIR/codex-test-report-$TIMESTAMP.md"
PHASE3_LOG="$WORKDIR/codex-phase3-$TIMESTAMP.log"

function check_codex () {
  if [[ ! -x "$CODEX_BIN" ]]; then
    echo "codex binary not found at $CODEX_BIN" >&2
    exit 1
  fi
}

check_codex

echo "== Phase 1 (gpt-5.1-codex-mini): data gathering ==" | tee "$PHASE1_LOG"
"$CODEX_BIN" exec -m gpt-5.1-codex-mini --sandbox workspace-write - <<'EOF' | tee -a "$PHASE1_LOG"
Please run `python3 phase1_runner.py` inside /lump/apps/dev-activity-report-skill and print only the JSON output produced by the script. After completing, mention the fingerprint stored in .phase1-cache.json.
EOF

echo
echo "Phase 1 complete. Fingerprint file (if created) is: $WORKDIR/.phase1-cache.json"

echo "== Phase 2 (gpt-5.3-codex): analysis/report ==" 
"$CODEX_BIN" exec -m gpt-5.3-codex --sandbox workspace-write --output-last-message "$PHASE2_TEMP" - <<'EOF'
You are a senior resume/portfolio writer. Read the JSON blob stored at /lump/apps/dev-activity-report-skill/.phase1-cache.json and produce:

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
"$CODEX_BIN" exec -m gpt-5.1-codex-mini --sandbox workspace-write - <<'EOF' | tee "$PHASE3_LOG"
Please `cd /lump/apps/dev-activity-report-skill` and run the following Python command:

python3 - <<'PY'
import json
from pathlib import Path

skill_dir = Path("/lump/apps/dev-activity-report-skill")
phase1_path = skill_dir / ".phase1-cache.json"
reports = []

if phase1_path.exists():
    data = json.loads(phase1_path.read_text())
    reports.append(f"phase1 fingerprint: {data.get('fingerprint')}")
else:
    reports.append("phase1 cache missing")
    data = {}

for proj in data.get("data", {}).get("cache_fingerprints", []):
    path = Path(proj["path"])
    cache = path / ".dev-report-cache.md"
    header = cache.read_text().splitlines()[0] if cache.exists() else "missing"
    reports.append(f"{proj['name']}: {header}")

print("\\n".join(reports))
PY

EOF

echo "Phase 3 log: $PHASE3_LOG"
