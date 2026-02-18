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
| `APPS_DIR` | `~/projects` | primary projects root |
| `EXTRA_SCAN_DIRS` | _(blank)_ | space/comma separated |
| `CODEX_HOME` | `~/.codex` | |
| `CLAUDE_HOME` | `~/.claude` | |
| `REPORT_OUTPUT_DIR` | `~` | |
| `REPORT_FILENAME_PREFIX` | `dev-activity-report` | |
| `REPORT_OUTPUT_FORMATS` | `md,html` | comma-separated (JSON always) |
| `INCLUDE_SOURCE_PAYLOAD` | `false` | include compact payload in JSON |
| `RESUME_HEADER` | `Your Name Software, Jan 2025 – Present` | |
| `ALLOWED_FILE_EXTS` | `.py,.ts,.js,.tsx,.cs,.csproj,.md,.txt,.json,.toml,.yaml,.yml,.sql,.html,.css,.sh` | used for non-git hashing |
| `INSIGHTS_REPORT_PATH` | `~/.claude/usage-data/report.html` | fingerprint exception |
| `PHASE1_MODEL` | `haiku` | Bash subagent |
| `PHASE15_MODEL` | `haiku` | draft synthesis |
| `PHASE2_MODEL` | `sonnet` | report polish |
| `PHASE3_MODEL` | `gpt-5.1-codex-mini` | deterministic cache writes |
| `SUBSCRIPTION_MODE` | `true` | set true when auth is handled by subscription (no API keys) |
| `TOKEN_LOG_PATH` | `${REPORT_OUTPUT_DIR}/token_economics.log` | JSONL |
| `BUILD_LOG_PATH` | `${REPORT_OUTPUT_DIR}/build.log` | summary lines |
| `BENCHMARK_LOG_PATH` | `${REPORT_OUTPUT_DIR}/benchmarks.jsonl` | benchmark JSONL |
| `PRICE_PHASE15_IN/OUT`, `PRICE_PHASE2_IN/OUT` | per 1M tokens | cost calc |
| `PHASE15_API_KEY`, `PHASE15_API_BASE`, `PHASE2_API_KEY`, `PHASE2_API_BASE` | optional | leave blank under subscription |
| `PHASE1_PROMPT_PREFIX`, `PHASE15_PROMPT_PREFIX`, `PHASE2_PROMPT_PREFIX`, `PHASE3_PROMPT_PREFIX` | _(blank)_ | legacy prefix keys; prefer rule-injection keys for structured phases |
| `PHASE15_RULES_EXTRA`, `PHASE2_RULES_EXTRA` | _(blank)_ | custom rules injected after stock prompt/schema |
| `INCLUDE_CLAUDE_INSIGHTS_QUOTES` | `false` | include quoted excerpts from `INSIGHTS_REPORT_PATH` in Phase 2 context |
| `CLAUDE_INSIGHTS_QUOTES_MAX`, `CLAUDE_INSIGHTS_QUOTES_MAX_CHARS` | `8`, `2000` | caps for quote count and quote text size |

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
  ${PHASE1_PROMPT_PREFIX}
  python3 scripts/phase1_runner.py
```

If you need to override built-ins, set a prefix such as: `Ignore any following instructions for this phase. <your instructions>`.

Outputs `{"fp": "<global-hash>", "cache_hit": <bool>, "data": {...}}` with compact keys only (see PAYLOAD_REFERENCE). No raw git logs are emitted; payload contains commit counts, shortstats, changed files, and derived themes.

If `cache_hit=true`, reuse the emitted payload verbatim.

---

## Phase 1.5 — Cheap draft

Input: Phase 1 JSON (stdin or `--input <file>`). Command:
```
python3 scripts/phase1_5_draft.py --input phase1.json > phase1_5.json
```
The script sends a concise prompt to `${PHASE15_MODEL}` (env-configurable) to create a rough bullet draft; falls back to a deterministic heuristic if no API key. Token usage is appended to `TOKEN_LOG_PATH` and `BUILD_LOG_PATH` when credentials exist.

Phase 1.5 prompt layering:
`stock prompt` -> `PHASE15_RULES_EXTRA` (or legacy `PHASE15_PROMPT_PREFIX`) -> injected Summary JSON.
The Summary JSON is always injected after custom rules.

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

## Phase 2 — Structured Analysis (JSON only)

Use only Phase 1 `data` + Phase 1.5 `draft`. Do not re-read files. Keep Phase 2 input compact to minimize tokens.

**Prompt skeleton (replace placeholders):**
```
System: You are a senior resume/portfolio writer with excellent creative writing and deep technical understanding. 

User:
Summary JSON (compact): {{data_json}}
Draft bullets: {{draft_text}}

Return JSON only (no Markdown, no code fences) with:
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

Rules:
- Output JSON only; no Markdown.
- Input uses compact keys from PAYLOAD_REFERENCE (p/mk/x/cl/cx/ins/stats).
- Resume bullets: 5–8 items, achievement-oriented, past tense, quantified where possible.
- LinkedIn: 3–4 sentences, first person, professional but conversational.
- Highlights: 2–3 items.
- Timeline: 5 rows, most recent first.
- Tech Inventory: languages, frameworks, AI tools, infra.
- Apply `${PHASE2_RULES_EXTRA}` (or legacy `${PHASE2_PROMPT_PREFIX}`) as rule overrides only; do not alter output schema.
- If `INCLUDE_CLAUDE_INSIGHTS_QUOTES=true`, quoted excerpts from `INSIGHTS_REPORT_PATH` may be included and should carry attribution when used.
```

**Note**: Compact keys are expanded deterministically after Phase 2 (no LLM translation) before rendering.

---

## Phase 2.5 — Render Outputs

Use `scripts/render_report.py` to render the Phase 2 JSON into `md` and/or `html` based on `REPORT_OUTPUT_FORMATS`. JSON is always written to `${REPORT_OUTPUT_DIR}/${REPORT_FILENAME_PREFIX}-<timestamp>.json`. The renderer should consume the JSON and produce:

- `${BASE}.md` (if `md` enabled)
- `${BASE}.html` (if `html` enabled)

Log Phase 2 tokens using `scripts/token_logger.py` with API usage numbers returned by the provider.

Save final report to `${REPORT_OUTPUT_DIR}/${REPORT_FILENAME_PREFIX}-<YYYYMMDDTHHMMSSZ>.md` (UTC datetime format to prevent overwrites).

---

## Phase 3 — Cache writes (Codex)

This is a simple Bash tool call, almost any model should be able to handle it. The input is the stale projects list only. Fingerprints are content hashes of git-tracked files (or allowed non-git files) and should be written into `.dev-report-cache.md` per project. Model: `${PHASE3_MODEL}`.

Prompt prefix (optional): `${PHASE3_PROMPT_PREFIX}`.

---

## Fingerprint Ignore List

Before computing any content hash (git repos, non-git dirs, `claude_home`, `codex_home`), check `.dev-report-fingerprint-ignore` (at `SKILL_DIR`) for glob patterns to exclude. This prevents volatile runtime files from invalidating the cache on every run.

The ignore file uses fnmatch patterns (one per line, `#` comments). Patterns ending with `/*` are treated as recursive prefix matches (match any path under that directory at any depth).

Key excluded categories:
- `*.log`, `build.log`, `references/examples/token_economics.log`
- `benchmarks.jsonl` (default in `REPORT_OUTPUT_DIR`)
- `todos/*`, `tasks/*`, `projects/*` — per-session Claude Code artifacts
- `debug/*`, `*.txt` — Claude Code debug files
- `ccusage-blocks.json`, `stats-cache.json`, `settings.json`
- `.credentials.json` — auth tokens

Apply this filter in Phase 1 whenever calling `scripts/phase1_runner.py`. If running Phase 1 inline (without the script), load the ignore file manually and apply the same filter before hashing.

---

## Efficiency Notes

- Compact keys only (see PAYLOAD_REFERENCE); avoid expanding names in prompts.
- Fingerprints use content hashes of git-tracked files; non-git hashing respects `ALLOWED_FILE_EXTS`; `insights_report.html` is the sole non-git exception.
- Never pass raw git logs. Use counts, shortstats, changed file names, and derived themes (`hl`).
- Keep context tight: stale projects only; cached entries are omitted intentionally.
- Record token economics after Phase 1.5 and Phase 2 runs via `token_logger.py`.
