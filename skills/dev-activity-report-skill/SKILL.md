---
name: dev-activity-report
description: Generates a professional activity summary from compact Phase 1 JSON and a cheap Phase 1.5 draft. Scans configurable app directories, extra fixed locations, ~/.claude/, and ~/.codex/, then produces resume bullets and a LinkedIn paragraph. Use ONLY when the user explicitly invokes /dev-activity-report. Do NOT auto-trigger from general questions about work history or projects.
---

# Dev Activity Report (token optimized)

Pipeline: Phase 1 data gather → Phase 1.5 draft (cheap model) → Phase 2 polish (single-shot) → Phase 3 cache writes.

Docs: compact key map in `references/PAYLOAD_REFERENCE.md`.

---

## Configuration (.env)

Load `.env` from the skill root. Copy `references/examples/.env.example` if missing.

To configure with agent assistance, run:
```
scripts/setup_env.py
```
This copies the example if needed, attempts auto-fill from environment, and prompts for key paths and models. Background runs use non-interactive setup; if required values are still missing, the run fails with a clear message.

| Key | Default | Notes |
|---|---|---|
| `APPS_DIR` | `/lump/apps` | primary projects root |
| `EXTRA_SCAN_DIRS` | `/usr/local/lib/mariadb` | space/comma separated |
| `CODEX_HOME` | `~/.codex` | |
| `CLAUDE_HOME` | `~/.claude` | |
| `REPORT_OUTPUT_DIR` | `~` | |
| `REPORT_FILENAME_PREFIX` | `dev-activity-report` | |
| `RESUME_HEADER` | `ngallodev Software, Jan 2025 – Present` | |
| `ALLOWED_FILE_EXTS` | `.py,.ts,.js,.tsx,.cs,.csproj,.md,.txt,.json,.toml,.yaml,.yml,.sql,.html,.css,.sh` | used for non-git hashing |
| `INSIGHTS_REPORT_PATH` | `~/.claude/usage-data/report.html` | fingerprint exception |
| `PHASE1_MODEL` | `haiku` | Bash subagent |
| `PHASE15_MODEL` | `haiku` | draft synthesis |
| `PHASE2_MODEL` | `sonnet` | report polish |
| `PHASE3_MODEL` | `gpt-5.1-codex-mini` | deterministic cache writes |
| `SUBSCRIPTION_MODE` | `true` | set true when auth is handled by subscription (no API keys) |
| `TOKEN_LOG_PATH` | `token_economics.log` | JSONL |
| `BUILD_LOG_PATH` | `build.log` | summary lines |
| `PRICE_PHASE15_IN/OUT`, `PRICE_PHASE2_IN/OUT` | per 1M tokens | cost calc |
| `PHASE15_API_KEY`, `PHASE15_API_BASE`, `PHASE2_API_KEY`, `PHASE2_API_BASE` | optional | leave blank under subscription |

---

## Phase 0 — optional insights snapshot

Check `INSIGHTS_REPORT_PATH`. If missing, warn and continue. If present, fold into `references/examples/insights/insights-log.md` (best-effort; skip if parsing fails).

---

## Phase 1 — Data gathering (Bash subagent)

Run as a single Bash tool call:
```
subagent_type: Bash
model: ${PHASE1_MODEL}
description: "Phase 1 dev-activity-report data collection"
prompt: |
  python3 scripts/phase1_runner.py
```

Outputs `{"fp": "<global-hash>", "cache_hit": <bool>, "data": {...}}` with compact keys only (see PAYLOAD_REFERENCE). No raw git logs are emitted; payload contains commit counts, shortstats, changed files, and derived themes.

If `cache_hit=true`, reuse the emitted payload verbatim.

---

## Phase 1.5 — Cheap draft

Input: Phase 1 JSON (stdin or `--input <file>`). Command:
```
python3 scripts/phase1_5_draft.py --input phase1.json > phase1_5.json
```
The script sends a concise prompt to `${PHASE15_MODEL}` (env-configurable) to create a rough bullet draft; falls back to a deterministic heuristic if no API key. Token usage is appended to `TOKEN_LOG_PATH` and `BUILD_LOG_PATH` when credentials exist.

Output JSON: `{"draft": "<text>", "usage": {...}, "cost": <float|null>}`

---

## Run Mode (default background)

By default, this skill runs **in the background** with no terminal output and no permission prompts. On completion, send a **terminal-notifier** notification stating the report path. Foreground output is only shown when explicitly requested.

Use the runner (models read from `.env`):
```
scripts/run_report.sh          # background, silent, notify on completion
scripts/run_report.sh --foreground
```

The runner uses `codex exec` with `--approval never --sandbox workspace-write` to avoid interactive permission prompts. If the user requests foreground execution, run the same code path but stream output.

---

## Phase 2 — Analysis (single-shot, polish the draft)

Use only Phase 1 `data` + Phase 1.5 `draft`. Do not re-read files.

**Prompt skeleton (replace placeholders):**
```
System: You are a senior developer writing a concise activity report. Stay terse.

User:
Summary JSON (compact): {{data_json}}
Draft bullets: {{draft_text}}

Write Markdown with exactly these headings:
## Overview
## Key Changes
## Recommendations
## Resume Bullets
## LinkedIn
## Highlights
## Timeline
## Tech Inventory

Rules:
- Keep bullets short; no meta commentary.
- Use markers mk + st to separate original vs forked.
- Pull AI workflow patterns from ins / cx / cl.
```

**Tiny few-shot (token-thrifty):**
```
Summary JSON: {"p":[{"n":"rag-api","cc":3,"fc":["api/router.py"],"hl":["perf","ai-workflow"]}],"mk":[],"cx":{"sm":{"2026-02":4}},"ins":[]}
Draft bullets: - rag-api: 3 commits; themes perf, ai-workflow

Output:
## Overview
- Refreshed rag-api with perf + AI workflow tweaks.

## Key Changes
- rag-api: perf-focused tweaks across api/router.py.

## Recommendations
- Ship perf benchmarks.

## Resume Bullets
- Boosted rag-api throughput by tightening router hot paths and validating AI pipeline hooks.

## LinkedIn
- Tuned rag-api for faster routes and smoother AI integration.

## Highlights
- Perf + AI workflow alignment.

## Timeline
- 2026-02: rag-api perf/AI tune-up.

## Tech Inventory
- Languages: Python
```

Log Phase 2 tokens using `scripts/token_logger.py` with API usage numbers returned by the provider.

Save final report to `${REPORT_OUTPUT_DIR}/${REPORT_FILENAME_PREFIX}-<YYYYMMDDTHHMMSSZ>.md` (UTC datetime format to prevent overwrites).

---

## Phase 3 — Cache writes (Codex)

Delegate to `/codex-job` with the stale projects list only. Fingerprints are content hashes of git-tracked files (or allowed non-git files) and should be written into `.dev-report-cache.md` per project. Model: `${PHASE3_MODEL}`.

---

## Efficiency Notes

- Compact keys only (see PAYLOAD_REFERENCE); avoid expanding names in prompts.
- Fingerprints use content hashes of git-tracked files; non-git hashing respects `ALLOWED_FILE_EXTS`; `insights_report.html` is the sole non-git exception.
- Never pass raw git logs. Use counts, shortstats, changed file names, and derived themes (`hl`).
- Keep context tight: stale projects only; cached entries are omitted intentionally.
- Record token economics after Phase 1.5 and Phase 2 runs via `token_logger.py`.
