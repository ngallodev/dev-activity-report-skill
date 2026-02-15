#!/usr/bin/env bash
set -euo pipefail

# Lightweight local harness to exercise the token-optimized pipeline without Codex CLI.
# Runs Phase 1 -> Phase 1.5 draft -> deterministic Phase 2 stub and writes an artifact.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$ROOT_DIR/skills/dev-activity-report-skill"
OUT_DIR="$ROOT_DIR/codex-testing-output"
mkdir -p "$OUT_DIR"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
phase1_json="$OUT_DIR/phase1-$ts.json"
phase15_json="$OUT_DIR/phase1_5-$ts.json"
report_md="$OUT_DIR/codex-test-report-$ts.md"

echo "Running Phase 1..."
python3 "$SKILL_DIR/scripts/phase1_runner.py" >"$phase1_json"

echo "Running Phase 1.5 draft..."
python3 "$SKILL_DIR/scripts/phase1_5_draft.py" --input "$phase1_json" >"$phase15_json"

echo "Synthesizing stub Phase 2 report (no external LLM)..."
python3 - "$phase1_json" "$phase15_json" "$report_md" <<'PY'
import json, sys, pathlib, datetime
phase1_path, phase15_path, out_path = sys.argv[1:4]
data = json.loads(pathlib.Path(phase1_path).read_text())
draft = json.loads(pathlib.Path(phase15_path).read_text())

p = data.get("data", {})
projects = p.get("p", [])
mk = p.get("mk", [])
cx = p.get("cx", {})

lines = []
lines.append("## Overview")
lines.append(f"- Stub report generated locally at {datetime.datetime.utcnow().isoformat()}Z.")
lines.append(f"- Projects analyzed: {len(projects)}; markers: {len(mk)}.")
lines.append("")
lines.append("## Key Changes")
for proj in projects[:8]:
    name = proj.get("n", "project")
    cc = proj.get("cc", 0)
    themes = ", ".join(proj.get("hl", [])) or "updates"
    lines.append(f"- {name}: {cc} commits; themes {themes}.")
if not projects:
    lines.append("- No stale projects in payload.")
lines.append("")
lines.append("## Recommendations")
lines.append("- Run full Phase 2 with configured model to polish the draft.")
lines.append("- Verify token logs once API credentials are set.")
lines.append("")
lines.append("## Resume Bullets")
draft_text = draft.get("draft", "").strip()
if draft_text:
    for ln in draft_text.splitlines():
        if ln.strip():
            lines.append(ln)
else:
    lines.append("- Draft unavailable (no API key).")
lines.append("")
lines.append("## LinkedIn")
lines.append("Stub: summarize once full Phase 2 is executed with a model.")
lines.append("")
lines.append("## Highlights")
lines.append("- Token-optimized pipeline exercised locally without external calls.")
lines.append("")
lines.append("## Timeline")
lines.append("- " + datetime.datetime.utcnow().strftime("%Y-%m-%d") + ": Local dry-run.")
lines.append("")
lines.append("## Tech Inventory")
languages = set()
for proj in projects:
    for f in proj.get("fc", []):
        ext = pathlib.Path(f).suffix
        if ext:
            languages.add(ext)
lines.append(f"- Languages: {', '.join(sorted(languages)) or 'n/a'}")
lines.append(f"- AI/LLM: pending full Phase 2 run.")
pathlib.Path(out_path).write_text("\n".join(lines))
PY

echo "Artifacts written:"
echo " - $phase1_json"
echo " - $phase15_json"
echo " - $report_md"
echo "Done."
