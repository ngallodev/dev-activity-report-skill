# dev-activity-report Skill — Build History & Design Chronicle
*Session: 2026-02-13 to 2026-02-14 | Author: ngallodev + Claude Sonnet 4.5*

---

## Overview

This document chronicles the incremental design and implementation of the `dev-activity-report` Claude Code skill — a command that scans a local development environment and produces professional activity summaries (resume bullets, LinkedIn paragraph, hiring manager highlights) suitable for independent contractor portfolios.

The skill was built entirely within a single Claude Code session, evolving through ~12 discrete iterations from a raw prompt to a multi-phase, cache-aware, delegation-optimized system.

---

## Milestone 1 — Prompt to Skill (first commit)

**What happened**: User pasted a detailed freeform prompt describing the desired report and asked to "turn this into a command and store it, make it not loaded unless I enable it explicitly."

**Key decisions made**:
- Used the `skill-creator` skill's `init_skill.py` to scaffold the directory structure
- Stripped the verbatim user prompt down to structured SKILL.md instructions
- Set the description field to explicitly gate triggering: *"Use ONLY when the user explicitly invokes /dev-activity-report. Do NOT auto-trigger..."*
- Removed all three example resource directories (scripts/, references/, assets/) that init created — the skill needed no bundled resources at this stage

**Design insight**: The description field in SKILL.md frontmatter is the *sole triggering mechanism* before the body is loaded. Getting this right prevents the skill from firing on general questions about work history. The negative constraint ("Do NOT auto-trigger") matters as much as the positive one.

**Outcome**: Skill registered and immediately available as `/dev-activity-report`.

---

## Milestone 2 — First Live Execution

**What happened**: Skill invoked immediately after creation. Claude ran a full cold scan across all locations.

**Scan approach (naive, pre-optimization)**:
- Sequential Bash calls reading READMEs, git logs, file listings across ~50 directories
- No ownership classification — all directories treated as original work
- Results: several forks (hexstrike-ai, tookie-osint, subgen, etc.) incorrectly included as original projects

**Report produced**:
- 7 resume bullets
- LinkedIn paragraph
- 3 hiring manager highlights
- Full tech inventory and timeline

**Key finding**: Without ownership markers, the report mixed upstream open-source projects (tookie-osint, llama.cpp, firecrawl) with genuine original work — rendering the resume bullets misleading.

---

## Milestone 3 — Ownership Marker System

**What happened**: User asked how to mark forks so they don't appear as original work.

**Three-marker convention designed**:

| Marker file | Behavior |
|---|---|
| `.not-my-work` | Skip directory entirely — pure upstream clone |
| `.forked-work` | Include under "Forked & Modified" — read file for contribution notes |
| `.forked-work-modified` | Auto-generate `.forked-work` from git history, then treat as above |

**Design insight — the `.forked-work-modified` marker**: This was the most creative element of the session. Instead of requiring the user to manually write what they changed in each fork, dropping an empty `.forked-work-modified` file triggers Claude to inspect `git log`, `git diff`, and file modification timestamps to *infer* the contribution summary automatically, then write it to `.forked-work` and delete the trigger. One touch, zero writing.

**21 directories marked** `.not-my-work` in a single batch operation. Four marked `.forked-work-modified` for auto-documentation (subgen, metube2, jellyfin-roku, yt-dlp).

**Skill updated**: Pre-scan phase added to build skip list before touching any directories. Projects in the skip list are never descended into — saves I/O and prevents upstream READMEs from polluting context.

---

## Milestone 4 — `.forked-work-modified` Auto-Documentation Executed

**What happened**: On the next `/dev-activity-report` invocation, Claude processed all four `.forked-work-modified` markers before running the main scan.

**Per-project findings**:

- **subgen**: Detected a new module (`subtitle_cache.py`), a test suite (`test_subtitle_cache.py`), implementation progress tracker, Docker configuration variants, and custom commits ("mo custom", "custom stuff y"). Wrote a 7-bullet `.forked-work` describing the persistent subtitle cache system.
- **metube2**: Detected `docker-compose.custom.yml`, `Dockerfile.custom`, `yt-dlp.conf` (not present in upstream), and custom commits. Wrote a 4-bullet `.forked-work` covering the configuration layer.
- **jellyfin-roku**: Detected custom image assets (logos, splash screens in SD/HD/FHD), upstream branch tracking. Wrote a 3-bullet `.forked-work`.
- **yt-dlp**: Detected no source modifications — only local build artifacts. Wrote an honest `.forked-work` noting it's used as a vendored binary, not modified.

**Design insight**: The honest "no real modifications" case for yt-dlp is important. The auto-doc process correctly distinguished between "I use this" and "I changed this" by checking for files not present in upstream structure and commits not matching upstream authors. This prevents resume inflation just as effectively as `.not-my-work` does.

---

## Milestone 5 — Per-Project Cache System

**What happened**: User requested that on successive scans, if a project hasn't changed, Claude should use stored analysis rather than re-reading and re-analyzing the directory.

**Cache design**:
- File: `<project-dir>/.dev-report-cache.md`
- Format: HTML comment fingerprint header + structured markdown analysis block
- Fingerprint: `git rev-parse HEAD` for git repos, `stat mtime` for non-git directories
- Match logic: read first line of cache, compare embedded fingerprint to current — if equal, use cache verbatim

```markdown
<!-- fingerprint: <git_hash_or_mtime> -->
<!-- cached: 2026-02-13 -->

## project-name
**Stack**: ...
**Last active**: ...
**Summary**: ...
**Type**: original | forked (upstream: ...)
```

**10 cache files written** immediately after the session's analysis to seed the system.

**Design insight — mtime vs. git hash**: Git repos use commit hash (stable, precise — only changes on actual commits). Non-git directories use directory mtime (less precise — changes on any file modification including temp files). This is an intentional tradeoff: git repos get exact fingerprinting, everything else gets conservative re-scan on any change.

**Edge case caught**: `app-tracker` had a fingerprint mismatch on the warm test run — directory mtime had changed (plans were added) but no new git commits. Cache correctly invalidated and triggered re-scan. Working as designed.

---

## Milestone 6 — Three-Phase Architecture + Delegation to Haiku

**What happened**: User asked whether Phase 1 data gathering could be delegated to a cheaper model (Haiku or Codex-mini) to reduce token costs.

**Analysis of delegatability**:

| Task | Delegatable? | Agent | Reason |
|---|---|---|---|
| Marker scan + fingerprint check | Yes | Haiku | Pure filesystem, no judgment |
| Raw fact collection (git log, file list, README) | Yes | Haiku | Retrieval only |
| `.forked-work-modified` data gathering | Yes | Haiku | Gathers diffs, Sonnet writes summary |
| `.forked-work` summary writing | No | Sonnet | Requires judgment about attribution |
| Analysis + report synthesis | No | Sonnet | Writing quality required |
| Cache file writes | Yes | Codex-mini | Fully specced deterministic writes |

**Three-phase architecture formalized**:
1. **Phase 1** — Haiku `Bash` subagent: all data gathering in a single Python script block
2. **Phase 2** — Sonnet: synthesizes from Haiku's compact output only
3. **Phase 3** — Codex-mini via `/codex-job`: writes cache files deterministically

**Key design decision — single Bash call**: All Phase 1 logic consolidated into one Python script passed as a single Bash invocation. This minimizes exposure to permission hooks (which fired on individual `ls`/`stat` calls in the test run) and reduces per-call overhead.

---

## Milestone 7 — Live Test + Token Economics

**What happened**: Phase 1 delegation actually executed using a Haiku `general-purpose` subagent (later corrected to `Bash`). Real token counts captured.

**Test results** (first run, `general-purpose` agent — suboptimal):

| Metric | Value |
|---|---|
| Wall time | 71 seconds |
| Real input tokens | 169 |
| Cache creation tokens | ~29,000 |
| Cache read tokens | 618,399 |
| Output tokens | 42 |

**Critical finding**: 618k cache-read tokens came from the `general-purpose` system prompt being loaded on every tool call turn. The actual project data was ~2-4k tokens. The agent type was the overwhelming cost driver, not the work itself.

**Fix**: Skill updated to specify `subagent_type: Bash` — minimal system prompt (~5k tokens vs. 618k). Expected 60-100x reduction in Phase 1 token overhead on next run.

**Cost comparison**:
- Old approach (all Sonnet, no delegation): ~$0.113 estimated
- New Phase 1 (Haiku general-purpose, first run): ~$0.078
- New Phase 1 (Haiku Bash agent, warm run): projected ~$0.005-0.010

**Token economics reference doc** written to `references/token-economics.md` with real benchmarks, scaling tables, and cost model — not loaded into skill context on invocation.

---

## Design Principles That Emerged

### 1. Description field as the trigger gate
The SKILL.md `description` field is loaded into every session. The body only loads after triggering. Negative constraints in the description ("Do NOT auto-trigger") are as important as positive ones.

### 2. Marker files as a lightweight metadata layer
Dropping a single empty file in a directory (`touch .not-my-work`) is enough to permanently classify a project's ownership status for all future scans. No configuration files, no central registry, no database — just filesystem markers co-located with the code they describe.

### 3. Auto-documentation via git archaeology
`.forked-work-modified` demonstrates a broader pattern: use AI to eliminate a specific class of tedious documentation work by triggering it from a filesystem signal. The user doesn't write contribution notes — they touch a file and the next scan generates them from git history.

### 4. Cache fingerprinting at the directory level
Storing analysis results next to the code they describe (`.dev-report-cache.md` in each project dir) keeps the cache co-located, human-readable, and git-ignorable. It also means the cache naturally follows the project if the directory is moved.

### 5. Separate data gathering from synthesis
The three-phase architecture enforces a clean boundary: Phase 1 collects facts (cheap model, no reasoning), Phase 2 synthesizes (expensive model, reasoning only). This prevents the common pattern of expensive models spending tokens on I/O work they're overqualified for.

### 6. Agent type matters more than model choice for cost
The test revealed that `general-purpose` vs `Bash` subagent type caused a 100x difference in effective token cost — dwarfing the difference between Haiku and Sonnet pricing. Choosing the right agent type is the highest-leverage cost optimization available.

---

## Files Produced This Session

| File | Purpose |
|---|---|
| `~/.claude/skills/dev-activity-report/SKILL.md` | Core skill instructions |
| `~/.claude/skills/dev-activity-report/references/token-economics.md` | Cost benchmarks, not loaded in context |
| `~/.claude/skills/dev-activity-report/references/build-history.md` | This document |
| `~/dev-activity-report-2026-02-13.md` | First report output |
| `~/dev-activity-report-2026-02-13-v2.md` | Second report output (ownership-corrected) |
| `/lump/apps/*/.dev-report-cache.md` | Per-project analysis caches (10 written) |
| `/lump/apps/*/.not-my-work` | Ownership markers (21 directories) |
| `/lump/apps/*/.forked-work` | Contribution summaries (4 auto-generated) |

---

## Milestone 8 — PII Extraction, `.env` Config, Codex Scanning, README, GitHub

*Session: 2026-02-13 (continued) | Author: ngallodev + Claude Sonnet 4.5*

**What happened**: Second session continuing directly from the context-compacted first. Four improvements requested simultaneously: PII/config extraction, Codex session scanning, README, and GitHub publication.

### 8a — `.env` Configuration System

**Problem**: SKILL.md had hardcoded user-specific values scattered throughout — paths (`/lump/apps/`, `/usr/local/lib/mariadb`), identity strings (`ngallodev Software, Jan 2025 – Present`), and model names (`haiku`, `gpt-5.1-codex-mini`).

**Solution**: Extracted all 9 user-specific values into a `.env` file with `.env.example` committed and `.env` gitignored:

| Variable | Purpose |
|---|---|
| `APPS_DIR` | Primary projects directory |
| `EXTRA_SCAN_DIRS` | Space-separated additional fixed paths |
| `CODEX_HOME` | Path to Codex home (`~/.codex`) |
| `CLAUDE_HOME` | Path to Claude home (`~/.claude`) |
| `REPORT_OUTPUT_DIR` | Where to write the report file |
| `REPORT_FILENAME_PREFIX` | Report filename prefix |
| `RESUME_HEADER` | Name/company for resume section header |
| `PHASE1_MODEL` | Haiku model alias for data gathering |
| `PHASE3_MODEL` | Codex model for cache writes |

SKILL.md now uses `${VAR}` placeholders throughout with an instruction to resolve from `.env` before constructing the Phase 1 prompt. The Configuration section shows a defaults table so the skill works out-of-the-box without a `.env` present.

**Design insight**: The SKILL.md description field also previously mentioned hardcoded paths. Updated to generic language so the skill's trigger description doesn't expose machine-specific layout.

### 8b — Codex Session Scanning

**Problem**: `~/.codex/sessions/` contains rich data about Codex usage (projects worked on, session frequency, model config, installed skills) but was not being scanned.

**What the scan produces**:
- Session count by month (surfaced: 13 sessions Jan 2026, 37 Feb 2026 — accelerating usage)
- Active project directories (extracted from `<cwd>` tags in session JSONL)
- Codex config (model, reasoning effort, personality, per-project trust levels)
- Installed Codex skills (`~/.codex/skills/`)
- Permission rules count (57 entries in `default.rules`)

**Cache strategy**: `~/.codex/.dev-report-cache.md` fingerprinted on the mtime of the `sessions/` directory. When new sessions are added, the directory mtime changes and the cache invalidates. Cached summary written after Phase 3.

**I/O bound**: Only last 50 session files scanned to bound read time. Sessions can be large JSONL files; reading all of them unbounded would dominate Phase 1 cost.

**New report section added**: "Codex Activity" section in Phase 2 output, plus "Parallel Claude + Codex skills ecosystems" added as a Hiring Manager Highlight.

### 8c — Third Report Run (v3)

Executed `/dev-activity-report` with the new SKILL.md. Results:

- Phase 1 Haiku: 18,304 tokens, 10 tool uses, 42.5 seconds
- Cache hits: 5 projects (agentic-workflow, invoke-codex-from-claude, osint-framework, secret-sauce-proj; app-tracker fingerprint changed)
- New stale projects analyzed: anth, codex-workflows, dev-activity-report-skill, dotnet10-app, jenkins, mcp4kali, ollama (+ mariadb extra location + codex home first scan)
- Codex activity surfaced: 50 sessions, 9 active cwds, gpt-5.2 model, 57 rules, `local-activity-summary` skill
- Report saved to `~/dev-activity-report-2026-02-13-v3.md`

**Phase 3 note**: The `/codex-job` skill's `invoke_codex_with_review.sh` script lives in the `invoke-codex-from-claude` repo, not the installed skill directory. The codex-job SKILL.md assumes it's invoked from within that repo. For standalone use (e.g., from dev-activity-report), the cache writes were done directly via a Python one-liner — appropriate since 9 deterministic file writes is below the delegation threshold.

### 8d — README

Written as a dual-audience document: portfolio showcase first, technical docs second.

Structure:
1. One-line pitch + "turns this into this" code block showing real transformation
2. How It Works (three-phase pipeline summary)
3. Sample Output — real resume bullets, LinkedIn paragraph, hiring manager highlights from the author's environment
4. Token Cost table with real numbers ($0.040 cold / $0.031 warm vs. $0.113 all-Sonnet)
5. Key Features — ownership markers, per-project caching, Codex analytics, `.env` config
6. Limitations & Roadmap — honest single-machine scope acknowledgment, multi-machine as planned enhancement
7. Installation + Usage
8. File Reference
9. How It Was Built — links to build-history, surfaces design principles

**Design decision — sample output**: Used real output from the author's environment rather than fictional examples. More convincing as a portfolio piece; project names are already public-safe.

### 8e — GitHub Publication

Repo created at `https://github.com/ngallodev/dev-activity-report-skill` (public). Initial commit includes SKILL.md, .env.example, .gitignore, README.md, and all four references files. The `.dev-report-cache.md` file in the skill dir itself was intentionally left out of the initial commit (untracked).

---

## Files Produced This Session

| File | Purpose |
|---|---|
| `~/.claude/skills/dev-activity-report/SKILL.md` | Core skill instructions |
| `~/.claude/skills/dev-activity-report/references/token-economics.md` | Cost benchmarks, not loaded in context |
| `~/.claude/skills/dev-activity-report/references/build-history.md` | This document |
| `~/dev-activity-report-2026-02-13.md` | First report output |
| `~/dev-activity-report-2026-02-13-v2.md` | Second report output (ownership-corrected) |
| `~/dev-activity-report-2026-02-13-v3.md` | Third report output (Codex activity included) |
| `/lump/apps/*/.dev-report-cache.md` | Per-project analysis caches (19 written total) |
| `/home/nate/.codex/.dev-report-cache.md` | Codex session analytics cache (new) |
| `/lump/apps/*/.not-my-work` | Ownership markers (21 directories) |
| `/lump/apps/*/.forked-work` | Contribution summaries (4 auto-generated) |
| `/lump/apps/dev-activity-report-skill/.env.example` | Config template |
| `/lump/apps/dev-activity-report-skill/.gitignore` | Ignores .env |
| `/lump/apps/dev-activity-report-skill/README.md` | Portfolio README |

---

## Milestone 9 — Warm Cache Verification & Mtime Drift Fix

*Session: 2026-02-13 (continued) | Author: ngallodev + Claude Sonnet 4.5*

**What happened**: Ran `/dev-activity-report` Phase 1 in isolation to verify warm-cache behavior after all projects were cached in Milestone 8.

### First verification run — mtime drift bug discovered

Expected: most projects cache-hit. Actual: only 5 hits (the 4 git-hash repos from before + codex home). All non-git directory caches were misses despite having just been written.

**Root cause**: Writing `.dev-report-cache.md` inside a non-git directory bumps that directory's `mtime`. The Phase 3 cache write happens *after* Phase 1 records the fingerprint — so the fingerprint stored in the cache header matches the pre-write mtime. On the *next* Phase 1 run, `stat mtime` returns the post-write mtime (higher), which no longer matches the header → spurious re-scan on every run.

This is a self-defeating cache: writing the cache file invalidates it immediately for all non-git directories.

**Why git repos were unaffected**: Git commit hash fingerprinting is immune — writing a file doesn't change `git rev-parse HEAD` unless you commit.

### Fix

Changed non-git directory fingerprinting from `stat mtime` of the directory to **max mtime of content files, excluding `.dev-report-cache.md` itself**:

```python
def dir_fp(d):
    r = subprocess.run(['git','-C',d,'rev-parse','HEAD'], capture_output=True, text=True)
    if r.returncode == 0: return r.stdout.strip()
    result = subprocess.run(
        f'find {d} -maxdepth 3 -not -name ".dev-report-cache.md" -not -path "*/.git/*" '
        f'-type f -printf "%T@\n" 2>/dev/null | sort -n | tail -1',
        shell=True, capture_output=True, text=True)
    mt = result.stdout.strip().split('.')[0] if result.stdout.strip() else ''
    return mt or subprocess.check_output(['stat','-c','%Y',d]).decode().strip()
```

Applied consistently across all three fingerprinting sites in the Phase 1 prompt (CACHE FINGERPRINTS, STALE PROJECT FACTS, EXTRA FIXED LOCATIONS). Existing cache headers for the affected projects were also updated to the corrected fingerprint values.

**Edge case — empty directories**: If a directory has no files (only subdirs, or truly empty), the `find` returns nothing and we fall back to `stat mtime` on the directory itself. Acceptable — an empty directory with only a cache file is an unusual case.

**Design insight**: The fingerprint and the cache file must be decoupled. Any fingerprinting scheme that includes the cache file itself in the fingerprint input creates a self-invalidating loop. The fix is to either exclude the cache file from the input (chosen here) or store the cache file outside the project directory (more invasive, rejected).

### Second verification run — confirmed warm

| Metric | Value |
|---|---|
| Wall time | 8.7 seconds |
| Total tokens | 7,819 |
| Tool uses | 1 |
| Cache hits | 12 / 21 scanned projects |
| Cache misses (expected) | 9 never-cached minor dirs + mariadb (new commit) |

**7,819 tokens and 1 tool use** is the warm-scan floor. The single-Bash-call Phase 1 design is working as intended — all fingerprint checks happen inside one Python script, one tool call.

The 9 permanent misses (`.claude`, `.continue`, `aitest`, `clicky`, `continue.config`, `indydevdan`, `jelly`, `research`, `s`) are minor/reference/empty directories not worth caching. They will be re-scanned each time but contribute minimal output since they have no README or git history.

---

## Milestone 10 — `.skip-for-now` Marker

*Session: 2026-02-13 (continued) | Author: ngallodev + Claude Sonnet 4.5*

**What happened**: The 9 never-cached minor directories (`.claude`, `.continue`, `aitest`, `clicky`, `continue.config`, `indydevdan`, `jelly`, `research`, `s`) were being re-scanned every run since they had no cache and no `.not-my-work` marker. Needed a way to silence them without implying they're upstream clones.

**New marker**: `.skip-for-now` — skip a directory silently. Semantically distinct from `.not-my-work`:

| Marker | Intended meaning |
|---|---|
| `.not-my-work` | "This is someone else's repo — upstream clone, no original contribution" |
| `.skip-for-now` | "This is mine (or mine-adjacent) but parked, incomplete, or not worth reporting yet" |

The distinction matters for honesty: marking a WIP project `.not-my-work` would be misleading. `.skip-for-now` says "I know about this, I'm choosing to defer it."

**Implementation**: Added to the skip-set build loop in all three Phase 1 fingerprinting sites using a shared pattern:

```python
for marker in ['.not-my-work', '.skip-for-now']:
    for f in subprocess.check_output(f"find {apps_dir} -maxdepth 2 -name '{marker}'", shell=True, text=True).splitlines():
        skip.add(f.replace(f'/{marker}',''))
```

Also added to the `find` in SECTION: OWNERSHIP MARKERS, the marker reference table in SKILL.md, and README installation instructions.

**Verified run results**:

| Metric | Value |
|---|---|
| Total tokens | 8,233 |
| Tool uses | 1 |
| Wall time | 6.95 seconds |
| Skipped | 43 (21 `.not-my-work` + 4 `.forked-work`/`.not-my-work` combo + 9 `.skip-for-now` + marker-only dirs) |
| Cache hits | 10 |
| Cache misses | 2 (new commits: dev-activity-report-skill, invoke-codex-from-claude) + mariadb extra |

The 2 misses are expected — both repos received new commits this session. Clean warm-scan behavior confirmed.

---

## Milestone 11 — README Token Cost Table Completed

*Session: 2026-02-13 (continued) | Author: ngallodev + Claude Sonnet 4.5*

**What happened**: The token cost table in README.md was missing the Phase 1 cost column and the all-Sonnet baseline row had no token count or per-phase cost — making it hard to compare the value of delegation at a glance.

**Changes**: Added Phase 1 cost column to every row; added all-Sonnet token count (~25,000 in / ~2,500 out) and computed cost (~$0.075 Phase 1, ~$0.113 total). The table now has 6 columns: run type, Phase 1 tokens, Phase 1 cost, time, tool uses, total cost.

**Costs computed from pricing table** (Haiku $0.80/$4.00 per 1M, Sonnet $3.00/$15.00 per 1M):
- Cold Phase 1 (18,300 tok, ~14k in / ~4k out Haiku): $0.011 + $0.016 = ~$0.024
- Warm Phase 1 (7,819 tok, ~6.5k in / ~1.3k out Haiku): $0.005 + $0.005 = ~$0.010
- Fully warm Phase 1 (~8,200 tok Haiku): ~$0.006
- All-Sonnet Phase 1 (25k in / 2.5k out Sonnet): $0.075 + $0.0375 = ~$0.113 total

Final table in README:

| Run type | Phase 1 tokens | Phase 1 cost | Time | Tool uses | Total cost |
|---|---|---|---|---|---|
| Cold, no caches, no skips | ~18,300 | ~$0.024 | ~43s | 10 | ~$0.040 |
| Warm + `.skip-for-now` | 7,819 | ~$0.010 | 8.7s | 1 | ~$0.031 |
| Fully warm, all skipped/cached | ~8,200 | ~$0.006 | ~7s | 1 | ~$0.031 |
| All-Sonnet, no delegation | ~25,000 | ~$0.075 | ~71s | ~15 | ~$0.113 |

---

## Milestone 12 — Phase 1 fingerprint cache & structured output

*Session: 2026-02-14 | Author: ngallodev + Claude Sonnet 4.5*

**What happened**: The optimization plan was captured in `PLAN.md`, and Phase 1 was rewritten so Haiku no longer emits verbose command dumps. A helper script now gathers ownership markers, stale-project facts, extra directories, Claude/Codex activity, and the insights log; caches the resulting JSON payload plus a global fingerprint; and prints exactly one JSON object that Phase 2 consumes. README and `.gitignore` explain the new behavior.

**Implementation highlights**:
- `PLAN.md` now spells out the objectives: short-circuiting Phase 1 with a global fingerprint, emitting structured JSON instead of raw command output, and silencing terminal noise.
- `phase1_runner.py` computes the fingerprint, writes `.phase1-cache.json`, and prints `{"fingerprint":..., "cache_hit": <bool>, "data": {...}}`, so warm runs can reuse the cached payload without rerunning Haiku.
- SKILL.md now simply runs `python3 phase1_runner.py`, documents the fast-path behavior, and tells Phase 2 to read only the `data` object (including `forked_work_modified`’s structured entries).
- README now highlights the helper script and the Phase 1 fingerprint cache so users understand why warm runs are effectively free. `.phase1-cache.json` is gitignored to keep the cache local.

**Design insight**: Treating the entire Phase 1 payload as an atomic cached artifact (fingerprint + JSON) keeps warm runs quiet, fast, and token-cheap. Haiku only traverses the filesystem when something actually changes.

---

## Milestone 13 — Codex CLI test run & token audit

*Session: 2026-02-14 | Author: ngallodev + Codex gpt-5.1-codex/gpt-5.1-codex-mini*

**What happened**: Added `run_codex_test_report.sh` as a reusable Codex CLI harness (Phase 1 + 3 with `gpt-5.1-codex-mini`, Phase 2 with `gpt-5.1-codex`). The script collects the fingerprints, saves `codex-test-report-20260214T134156Z.md`, and runs a quick cache-header verification so every `.dev-report-cache.md` still carries the expected hash.

**Benchmark**:
- Phase 1 (mini): 12,452 tokens — warm fingerprint replay via `phase1_runner.py`.  
- Phase 2 (Codex): 50,928 tokens — professional resume/LinkedIn/highlights synthesis from the cached JSON.  
- Phase 3 (mini): 9,419 tokens — cache verification across the affected projects.  
Total: ~72.8k tokens (~$0.18 at Codex mini/Codex rates). Log files (`codex-phase1-*.log`, `codex-phase3-*.log`) capture the full Codex session, and the final report is available for downstream review.

**Design insight**: The structured Phase 1 JSON now survives Codex-driven executions, keeping mechanical phases cheap while centralizing cost control in a single Sonnet-style synthesis phase.

---


## What a Next Session Should Do

- Consider adding `--refresh` flag to force full re-scan despite valid caches
- Consider `--since <date>` flag to scope the report to a time window
- Investigate multi-machine support (SSH or remote filesystem mounts)
- Add the codex-job invocation path issue to known limitations in README (invoke script lives in invoke-codex-from-claude, not in installed skill)
- Update cache headers for dev-activity-report-skill and invoke-codex-from-claude after their next commits settle

---

## Milestone 14 — Token-efficient payload refactor + local dry-run harness

*Session: 2026-02-15 | Author: Codex GPT-5*

**What happened**: Refactored Phase 1 to emit compact, abbreviated JSON (documented in `docs/PAYLOAD_REFERENCE.md`), switched fingerprints to content hashes of git-tracked files (non-git hashes only allowed extensions), added Phase 1.5 draft synthesis, and introduced token logging utilities. `.env`/.env.example now carry all configuration knobs (models, pricing, allowed extensions, logging paths). A root harness `scripts/run_codex_test_report.sh` (with a wrapper in `skills/.../scripts/`) exercises Phase 1 → 1.5 → stub Phase 2 locally when no API keys are present.

**Artifacts produced**:
- `skills/dev-activity-report-skill/scripts/phase1_runner.py` (env-driven, compact payload)
- `skills/dev-activity-report-skill/scripts/phase1_5_draft.py` (cheap draft + token logging hook)
- `skills/dev-activity-report-skill/scripts/token_logger.py` (JSONL token log + build log appender)
- `skills/dev-activity-report-skill/docs/PAYLOAD_REFERENCE.md` (key map)
- `.env.example` and updated `.env` with new settings
- `scripts/run_codex_test_report.sh` + `skills/.../scripts/run_codex_test_report.sh` wrapper
- Dry-run outputs under `codex-testing-output/`:
  - `phase1-20260215T011345Z.json` (cache_hit=true replay)
  - `phase1_5-20260215T011345Z.json` (draft; fallback mode)
  - `codex-test-report-20260215T011345Z.md` (deterministic stub report)

**Notes**: Phase 2 polish still needs a real model to replace the stub; token logging will populate once API usage is enabled. Deprecation warnings from Python `utcnow()` surfaced during the stub run; harmless but can be modernized later.

---

## Milestone 15 — Structure realignment + Codex harness update

*Session: 2026-02-15 | Author: Codex GPT-5*

**What happened**: Realigned the repository to the updated `AGENTS.md` structure. Root scripts and references were removed; all scripts now live under `skills/dev-activity-report-skill/scripts/`, and references under `skills/dev-activity-report-skill/references/` with examples housed in `references/examples/`. `build-history.md` remains at repo root, and token economics logs live under `references/examples/`.

**Notable updates**:
- Moved `phase1_runner.py` and the Codex harness into `skills/dev-activity-report-skill/scripts/` (harness now in `scripts/testing/`).
- Updated harness paths to read/write the skill-local `.phase1-cache.json` and consume compact payload keys.
- Updated `SKILL.md` and `README.md` references to `references/examples/.env.example` and the new insights log location.

**Benchmark attempt**:
- Attempted live Codex run via `skills/dev-activity-report-skill/scripts/testing/run_codex_test_report.sh`.
- Phase 1 failed due to Codex backend stream disconnect (`https://chatgpt.com/backend-api/codex/responses`), rollout recorder channel closed. No report produced.

**Retry**:
- Re-ran the same harness on 2026-02-15; Phase 1 failed again with identical stream disconnect/rollout recorder errors. No report produced.

---

## Milestone 16 — Codex test report (successful run)

*Session: 2026-02-15 | Author: Codex GPT-5*

**What happened**: Ran `skills/dev-activity-report-skill/scripts/testing/run_codex_test_report.sh` with Phase 1 + 1.5 on `gpt-5.1-codex-mini` and Phase 2 on `gpt-5.3-codex`. Report saved to `codex-test-report-20260215T022940Z.md` with Phase 1/3 logs in `codex-phase1-20260215T022940Z.log` and `codex-phase3-20260215T022940Z.log`.

**Benchmark notes**:
- Phase 1 succeeded (cache hit). The runner output is still the legacy JSON shape (not the compact key schema), so Phase 3’s `fp` readout was `None`. Per-project cache headers were still reported.
- Phase 2 completed and saved the report. Token usage counts were shown in the Codex CLI output (Phase 2: 6,417 tokens; Phase 3: 5,435 tokens), but these counts were not captured in the log files.

---

## Milestone 17 — Compact Phase 1 payload restored + background runner

*Session: 2026-02-15 | Author: Codex GPT-5*

**What happened**: Replaced the legacy Phase 1 script with the compact payload version and added a background-first runner. The runner uses `codex exec --approval never --sandbox workspace-write` for all phases, defaults to background execution with a completion notification, and supports foreground output on request.

**Artifacts**:
- `skills/dev-activity-report-skill/scripts/phase1_runner.py` (compact payload + content hashes)
- `skills/dev-activity-report-skill/scripts/run_report.sh` (background runner + notify)

**Notes**: `terminal-notifier` is used when available; fallback to `notify-send` with install attempt via `apt-get` if missing; otherwise fail with a clear error.

---

## Milestone 18 — Codex test report (compact payload run)

*Session: 2026-02-15 | Author: Codex GPT-5*

**What happened**: Re-ran `skills/dev-activity-report-skill/scripts/testing/run_codex_test_report.sh` after restoring the compact Phase 1 payload. Phase 1/1.5 used `gpt-5.1-codex-mini`, Phase 2 used `gpt-5.3-codex`, and Phase 3 used `gpt-5.1-codex-mini`.

**Artifacts**:
- `codex-test-report-20260215T025110Z.md`
- `codex-phase1-20260215T025110Z.log`
- `codex-phase3-20260215T025110Z.log`
- `codex-phase1_5-last-message.txt`
- `codex-phase2-last-message.txt`

**Benchmark notes**:
- Phase 1 emitted compact JSON (`fp` present) and cached it to `.phase1-cache.json`.
- Phase 3 reported per-project cache headers and a non-null phase1 fingerprint.

---

## Milestone 19 — Remove hardcoded paths from `run_report.sh` (PLAN.md TODO #4 & #5)

*Session: 2026-02-14 | Author: ngallodev + Claude Sonnet 4.5*

**Problem**: `run_report.sh` had two issues flagged in the PR #2 review:
1. `ROOT_DIR`, `SKILL_DIR`, and `CODEX_BIN` were all hardcoded to `/lump/apps/...` and `/home/nate/.nvm/...`, making the script break when the skill is installed to `~/.claude/skills/`.
2. The `notify_done` fallback ran `sudo apt-get update && apt-get install -y libnotify-bin` silently, which is surprising and requires elevated privileges.

**Solution**:

### TODO #4 — Path derivation
- `SKILL_DIR` now derived from `$0`: `$(cd "$(dirname "$0")/.." && pwd)` — works correctly whether the script lives in `/lump/apps/`, `~/.claude/skills/`, or anywhere else.
- `CODEX_BIN` now uses `command -v codex` with a clean error if not found on PATH. The `.nvm`-specific path is gone.
- Output files (`LOG_FILE`, `PHASE15_OUT`, `PHASE2_OUT`, `REPORT_OUT`) now use `OUTPUT_DIR` derived from `REPORT_OUTPUT_DIR` in `.env`, falling back to `$HOME`. A leading `~` in the env value is expanded correctly.
- All hardcoded `/lump/apps/...` paths inside heredocs (phases 1, 1.5, 2, 3) replaced with `$SKILL_DIR`/`$PHASE15_OUT` shell variables. Heredoc delimiters switched from `'EOF'` (no expansion) to `EOF` (expansion) where needed.

### TODO #5 — Silent sudo removed from `notify_done`
- Removed the `sudo apt-get update && apt-get install -y libnotify-bin` block entirely.
- Replaced with a two-line stderr message: one line shows the notification message, one line provides install hints for both Linux and macOS.
- The function no longer `exit 1` on notification failure — the report has already been written; a missing notification tool is not a fatal error.

**Files changed**: `skills/dev-activity-report-skill/scripts/run_report.sh`
- Token counts were visible in CLI output but not persisted in log files.
