---
name: dev-activity-report
description: Generates a professional activity summary from local development environment, Claude Code session history, and Codex session history. Scans configurable app directories, extra fixed locations, ~/.claude/, and ~/.codex/, then produces resume bullets and a LinkedIn summary paragraph. Use ONLY when the user explicitly invokes /dev-activity-report. Do NOT auto-trigger from general questions about work history or projects.
---

# Dev Activity Report

Produce a professional activity summary. Follow the phased workflow below to minimize token usage.

---

## Configuration

Before running, read `.env` from the skill base directory (or the user's home directory) to load runtime config. If `.env` is not present, use the defaults shown. The `.env.example` file in this skill's directory documents all available variables.

Key variables and defaults:

| Variable | Default |
|---|---|
| `APPS_DIR` | `/lump/apps` |
| `EXTRA_SCAN_DIRS` | `/usr/local/lib/mariadb` |
| `CODEX_HOME` | `~/.codex` |
| `CLAUDE_HOME` | `~/.claude` |
| `REPORT_OUTPUT_DIR` | `~` |
| `REPORT_FILENAME_PREFIX` | `dev-activity-report` |
| `RESUME_HEADER` | `ngallodev Software, Jan 2025 – Present` |
| `PHASE1_MODEL` | `haiku` |
| `PHASE3_MODEL` | `gpt-5.1-codex-mini` |
| `SKILL_DIR` | directory containing this SKILL.md file |

`SKILL_DIR` is not set in `.env` — resolve it at runtime as the directory containing this SKILL.md file (e.g. `~/.claude/skills/dev-activity-report`).

Substitute all `${VAR}` references below with the resolved values before constructing the Phase 1 prompt.

---

## Phase 0 — Capture Insights Snapshot (optional, best-effort)

Before data gathering, check whether a Claude Code insights report exists at `~/.claude/usage-data/report.html`. This file is only present after the user has run `/insights`.

- If the file **does not exist**: print a one-line warning — `Note: no /insights report found at ~/.claude/usage-data/report.html — run /insights to include usage patterns in the log.` — then continue to Phase 1.
- If the file **exists**: extract the following fields from the HTML and append a new dated entry to `references/insights/insights-log.md` in this skill's directory (create the file if missing, using the existing log as a template):
  - Date (today's date)
  - Session/message/line/file/day stats (from `.stats-row`)
  - Project areas with session counts (from `.project-areas`)
  - Usage pattern summary (from `.narrative` key insight)
  - Wins (from `.big-wins` titles + descriptions, condensed)
  - Friction categories (from `.friction-categories` titles + condensed description)
  - Top tools used (from chart data)
  - Outcomes (fully/mostly achieved counts)

**Do not fail or halt if parsing the HTML is imperfect** — extract what you can and skip missing fields. This is a best-effort enrichment step.

The insights log lives at: `${SKILL_DIR}/references/insights/insights-log.md`

---

## Phase 1 — Data Gathering (delegated to subagent)

**Do not run these commands yourself.** Launch a `Bash` subagent (not `general-purpose`) via the Task tool with `model: ${PHASE1_MODEL}`. Using `subagent_type: Bash` avoids loading the full general-purpose system prompt — significantly reducing cache overhead (618k cache-read tokens vs. expected ~5k with `general-purpose`).

Task tool call:
```
subagent_type: Bash
model: ${PHASE1_MODEL}
description: "Phase 1 dev-activity-report data collection"
prompt: |
  python3 phase1_runner.py
```

`phase1_runner.py` (new at the skill root) reads `${APPS_DIR}`, `${EXTRA_SCAN_DIRS}`, `${CLAUDE_HOME}`, `${CODEX_HOME}`, and the insights log, then:
1. Computes a global fingerprint for all datasets and compares it against `.phase1-cache.json`.
2. If the fingerprint is unchanged, it short-circuits, re-emits the cached JSON payload, and exits. No extra commands, no banners, no permission errors spill into the terminal.
3. If anything changed, it gathers the structured payload (ownership markers, cache fingerprints, stale-project facts, `.forked-work-modified` context, extra directories, Claude/Codex activity, and the insights log), writes the fingerprint + payload back into `.phase1-cache.json`, and prints a single JSON object: `{"fingerprint": <hash>, "cache_hit": false, "data": {...}}`.

Always wait for the subagent to finish. Phase 2 must consume only the JSON printed by this script; there are no `find`/`git` dumps anymore, just the `data` dictionary in the object above.

Wait for the subagent to return all output before proceeding.

### 1b. Process `.forked-work-modified` (if any)

If the Phase 1 JSON payload contains entries under `data.forked_work_modified`, each record already includes the git log, diff file names, and recent files that triggered the marker. Use that structured context to write a concise (3-6 bullet) `.forked-work` note, then delete the `.forked-work-modified` file. This step still requires judgment — keep the summary upstream-crediting and limit yourself to the data the script already collected.

---

## Phase 2 — Analysis (synthesize from gathered facts only)

Using only the data collected in Phase 1 (the JSON the script prints, specifically the object under the `data` key; do not re-read any files), produce:

### Organize into

1. **Original work** — projects with no marker file
2. **Forked & modified** — projects with `.forked-work` (credit upstream, describe only your changes)
3. **Codex activity** — sessions, projects Codex was used on, notable patterns
4. **Technical problems solved** — 4-6 items max, one sentence each
5. **AI workflow patterns** — 3-5 items, one sentence each (include Claude + Codex collaboration patterns; if INSIGHTS LOG section is present, use its workflow patterns and wins as additional context)
6. **Tech inventory** — one line per category: Languages, Frameworks, AI/LLM, Infra
7. **Timeline** — 5-6 rows, most recent first

### Format A — Resume Bullets
5–8 bullets. Achievement-oriented, quantified where possible, past tense, action verbs.
Header: `${RESUME_HEADER}`

### Format B — LinkedIn Paragraph
3–4 sentences. First person, professional but conversational.

### Hiring Manager Highlights
2–3 items. Flag genuine engineering depth and non-obvious AI integration.

---

## Phase 3 — Write per-project cache files (delegated to Codex)

For each project that was re-analyzed (including extra fixed locations and Codex home if stale), delegate cache file writes to Codex via `/codex-job`. Provide the full list of files and their content in a single task.

Codex task prompt:
```
Write the following files exactly as specified. Each file should be created/overwritten with the content shown. No other changes.

FILE: ${APPS_DIR}/<project>/.dev-report-cache.md
<!-- fingerprint: <hash> -->
<!-- cached: <YYYY-MM-DD> -->

## <project-name>

**Stack**: <stack>
**Last active**: <date>
**Summary**: <2-4 sentence summary from Phase 2 analysis>
**Type**: original | forked (upstream: <repo>)

[repeat for each stale project]

FILE: ${CODEX_HOME}/.dev-report-cache.md   (only if CODEX ACTIVITY was re-scanned)
<!-- fingerprint: <sessions_mtime> -->
<!-- cached: <YYYY-MM-DD> -->

## codex-activity

**Model**: <model from config.toml>
**Skills**: <skill names>
**Sessions**: <summary of session counts by month>
**Active projects**: <cwds seen>
**Summary**: <2-3 sentence summary of Codex usage patterns>
```

Model: `${PHASE3_MODEL}` — fully deterministic, no reasoning required.

---

## Save Report

Save the final report to `${REPORT_OUTPUT_DIR}/${REPORT_FILENAME_PREFIX}-<YYYY-MM-DD>.md`.

---

## Ownership Marker Reference

| File | Behavior |
|---|---|
| `.not-my-work` | Skip entirely — upstream clone, no original work |
| `.skip-for-now` | Skip entirely — parked, incomplete, or not yet worth reporting |
| `.forked-work` | Include under "Forked & Modified"; read file for contribution notes |
| `.forked-work-modified` | Auto-generate `.forked-work` from git history, then treat as above |
| *(none)* | Original work |

---

## Efficiency Notes

- Run Phase 1 as a **single Bash call** containing all Python logic — minimizes hook exposure and reduces per-call overhead
- Read as few files as possible — README + plan.md only per project; skip everything else
- Use cached analysis whenever fingerprint matches; don't re-read or re-analyze
- Skip `node_modules/`, `venv/`, `bin/`, `obj/`, `.git/` always
- Codex session files are large — scan only the last 50 session files to bound I/O; cache the result in `${CODEX_HOME}/.dev-report-cache.md`
- See `references/token-economics.md` for cost benchmarks and real test results (not loaded into context)
