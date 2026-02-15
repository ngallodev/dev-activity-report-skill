# dev-activity-report

A Claude Code skill that scans your local development environment — git repos, project directories, Claude session history, Codex session history — and generates professional activity summaries ready to paste into a resume, LinkedIn profile, or hiring manager email.

**It turns this:**
```
/lump/apps/
  secret-sauce-proj/   (git: 47 commits, Feb 2026)
  invoke-codex-from-claude/
  osint-framework/
  ...
~/.codex/sessions/
  50 session rollout files across Jan-Feb 2026
```

**Into this:**

> *Designed and codified a human-Claude-Codex orchestration system with formal task readiness gates, risk-tiered routing, per-task-type delegation metrics, and a self-tightening spec feedback loop triggered when rolling success rates fall below 70%*

---

## What It Does

`/dev-activity-report` now runs a four-step, token-thrifty pipeline:

1. **Phase 1 — Data gathering** (`phase1_runner.py` via Bash subagent, `${PHASE1_MODEL}`): scans the configured paths, computes content-based fingerprints (git-tracked files only), and emits a **compact JSON payload** (abbreviated keys documented in `docs/PAYLOAD_REFERENCE.md`). Cached runs short-circuit by re-emitting the previous payload.
2. **Phase 1.5 — Draft synthesis** (`phase1_5_draft.py`, `${PHASE15_MODEL}`): cheap model creates a rough bullet draft from the Phase 1 JSON. Falls back to a deterministic heuristic if no API key.
3. **Phase 2 — Polish** (`${PHASE2_MODEL}`): single-shot prompt that ingests the compact JSON + draft and produces the final report with fixed headings (Overview, Key Changes, Recommendations, Resume Bullets, LinkedIn, Highlights, Timeline, Tech Inventory). No raw git logs are ever loaded.
4. **Phase 3 — Cache writes** (`${PHASE3_MODEL}`): writes per-project `.dev-report-cache.md` files using the new content-hash fingerprints to keep future scans warm.

**Result:** A dated `.md` file at `~/dev-activity-report-YYYY-MM-DD.md` plus token_economics/build logs capturing Phase 1.5 + Phase 2 usage.

---

## Sample Output

The following is real output generated from this author's environment.

### Resume Bullets

**ngallodev Software, Jan 2025 – Present**

- Architected a .NET 9 RAG pipeline API with multi-layer document/chunk model, EF Core + SQLite persistence, background ingestion channel, and service interface contracts; implemented using a structured multi-agent Codex execution plan with per-task model selection and sequential build verification
- Designed and codified a human-Claude-Codex orchestration system with formal task readiness gates, risk-tiered routing, per-task-type delegation metrics, and a self-tightening spec feedback loop triggered when rolling success rates fall below 70%
- Built `invoke-codex-from-claude`, a Claude Code skill wrapping `codex exec` with push-notification callbacks, structured JSON run logs, and one-command install/uninstall — operationalizing a 50-session Claude+Codex collaboration loop across 6 weeks
- Engineered a MariaDB dual-mode bulk loading toolkit achieving 50,000–500,000+ rows/second on a 256GB/28-core server, including automated mode-switching SQL scripts, performance configuration, real-time monitoring, and data repair utilities
- Developed a full-stack OSINT intelligence platform (.NET 8 + React 18/TypeScript + MariaDB + Docker + Ollama) with pluggable integrations for SpiderFoot, Sherlock, and theHarvester, and local LLM-backed analysis
- Extended open-source `subgen` with a persistent, thread-safe subtitle cache module — Docker-persistent, test-covered, with CLI management — reducing startup scan time on large media libraries
- Built `dev-activity-report-skill`, a self-documenting portfolio tool that scans local dev environments, performs per-project cache fingerprinting, and auto-generates resume bullets via a three-phase Claude+Haiku+Codex pipeline — reducing scan cost ~65% through model delegation

### LinkedIn Summary

> Over the past year I've been building at the intersection of software engineering and practical AI orchestration — not just using AI tools, but architecting the workflows that make multi-agent systems reliable and measurable. I designed a human-Claude-Codex delegation pipeline with formal readiness gates, risk routing, and a metrics feedback loop that auto-tightens specs when failure rates spike, and built the `invoke-codex-from-claude` CLI tooling to operationalize it across 50+ Codex sessions in six weeks. On the product side I've built a .NET 9 RAG pipeline, a full-stack OSINT platform with local LLM integration, a high-throughput MariaDB bulk-loading toolkit for a 256GB server, and a self-documenting dev activity scanner that turns git history into resume bullets via a cost-optimized Claude+Haiku+Codex pipeline. The through-line is the same everywhere: engineering real systems that happen to use AI, rather than AI demos that happen to look like systems.

### Hiring Manager Highlights

**1. Delegation metrics + self-tightening learning loop**
A global `delegation-metrics.jsonl` tracks every Codex job — model, cost, duration, status, failure class, retry count. Every 10 jobs per task type, rolling success rate is computed; if it drops below 70%, specs tighten automatically. This is operational infrastructure *around* AI to make it reliable at scale.

**2. Parallel Claude + Codex skills ecosystems**
Skills infrastructure exists for both Claude (`~/.claude/skills/`) and Codex (`~/.codex/skills/`), with consistent invocation patterns and per-agent trust tiering. 50 Codex sessions in 6 weeks across core projects, operating under 57 curated permission rules.

**3. `dev-activity-report-skill` itself**
A three-phase pipeline (Haiku data gathering → Sonnet synthesis → Codex cache writes) that scans git history, performs per-project cache fingerprinting, includes Codex session analytics, and auto-generates resume bullets — with measured 65% cost reduction from model delegation. The tool itself is the demonstration.

---

## Token Cost

Real measurements from a ~55-project environment (21 `.not-my-work`, 9 `.skip-for-now`, ~12 cached, 3 stale):

| Run type | Phase 1 tokens | Phase 1 cost | Phase 1 time | Tool uses | Total cost |
|---|---|---|---|---|---|
| Cold scan, no caches, no skips | ~18,300 | ~$0.024 | ~43s | 10 | **~$0.040** |
| Warm scan, 12 hits + `.skip-for-now` | **7,819** | **~$0.010** | **8.7s** | **1** | **~$0.031** |
| Fully warm, all skipped/cached | **~8,200** | **~$0.006** | **~7s** | **1** | **~$0.031** |
| All-Sonnet, no delegation (original) | ~25,000 | ~$0.075 | ~71s | ~15 | **~$0.113** |

**~65% total cost savings** from delegating off Sonnet. The warm Phase 1 is effectively free at Haiku rates — Phase 2 Sonnet synthesis (~$0.025) is the irreducible cost floor regardless of caching.

Token logging is now automated: Phase 1.5 and Phase 2 append JSON lines to `token_economics.log` and summary lines to `build.log` via `scripts/token_logger.py`.

The `.skip-for-now` marker had a meaningful impact on its own: dropping 9 directories reduced Phase 1 from 18,304 tokens (~$0.024) to 8,233 (~$0.010) — a 55% reduction in data-gathering cost, independent of caching.

The new Phase 1 fingerprint cache takes things further: once `phase1_runner.py` has built a JSON payload, reruns with the same fingerprint simply reprint that payload and never re-run the Haiku scan, so the marginal cost becomes Phase 2 only.

> Full benchmarks, scaling tables, and real token counts in `references/token-economics.md`.

---

## Key Features

### Ownership classification
Three marker files classify project ownership without any central registry:

| File | Behavior |
|---|---|
| `.not-my-work` | Skip entirely — upstream clone, no original work |
| `.skip-for-now` | Skip entirely — parked, incomplete, or not yet worth reporting |
| `.forked-work` | Include under "Forked & Modified" with your contribution notes |
| `.forked-work-modified` | Auto-generate `.forked-work` from git archaeology, then promote |

The `.forked-work-modified` pattern is especially useful: drop an empty file in a forked repo, and the next scan uses `git log`, `git diff`, and file modification times to infer what you changed — writing the summary without you having to type it.

### Per-project caching
Each scanned project gets a `.dev-report-cache.md` with a fingerprint header:
```markdown
<!-- fingerprint: <git-hash-or-mtime> -->
<!-- cached: 2026-02-13 -->

## project-name
**Stack**: ...
**Summary**: ...
```

Fingerprints are now **content hashes of git-tracked files** (non-git directories hash only allowed extensions from `ALLOWED_FILE_EXTS`), eliminating false positives from mtimes or cache file writes. When the fingerprint matches, the cached analysis is used verbatim.

### Phase 1 fingerprint cache
`phase1_runner.py` also builds a global fingerprint across ownership markers, project directories, extras, Claude data, Codex sessions, and the insights log. The fingerprint and the structured JSON payload are stored in `.phase1-cache.json`; if a rerun finds no changes it simply reprints that JSON (Haiku never re-traverses the tree). The upshot: warm runs emit exactly one JSON object and trimming Phase 1 output costs almost nothing.

### Compact payload + cheap draft
Phase 1 emits abbreviated JSON keys (documented in `docs/PAYLOAD_REFERENCE.md`) with only the essentials: commit counts, shortstats, changed files, and derived themes. Phase 1.5 uses a low-cost model to turn that JSON into a rough draft, which Phase 2 simply polishes — minimizing Sonnet tokens.

### Codex session analytics
Scans `~/.codex/sessions/` to surface Codex usage patterns — sessions by month, active project directories, installed skills, configured model — and includes them in the report and cache.

### Configurable via `.env`
All user-specific values (paths, identity, models) live in a `.env` file that's gitignored. The repo ships `.env.example` — copy and fill in once, never touch again.

---

## Limitations & Roadmap

**Current limitations:**
- Single-machine only. Scans the local filesystem; no support for remote hosts, SSH targets, or networked development environments.
- One `APPS_DIR` at a time. The `EXTRA_SCAN_DIRS` variable handles additional fixed paths, but multiple peer-level app directories require SKILL.md extension.
- No `--refresh` flag. To force a full re-scan despite valid caches, manually delete `.dev-report-cache.md` files or pass `--refresh` (not yet implemented).
- Non-git directory fingerprinting uses mtime, which can be noisy (temp files trigger re-scans).

**Planned enhancements:**
- Multi-machine support via SSH or remote filesystem mounts
- `--refresh` flag to force full re-scan
- `--since <date>` to scope the report to a time window
- Multiple `APPS_DIR` entries
- Smarter non-git fingerprinting (content hash of key files)

---

## Installation

### Prerequisites

- [Claude Code](https://claude.ai/claude-code) CLI installed and authenticated
- Claude Code skills support enabled

### Install the skill

**Option A — Clone and install directly:**
```bash
git clone https://github.com/ngallodev/dev-activity-report-skill
cp -r dev-activity-report-skill ~/.claude/skills/dev-activity-report
```

**Option B — Manual:**
Copy `SKILL.md` and the `references/` directory to `~/.claude/skills/dev-activity-report/`.

### Configure

```bash
cp ~/.claude/skills/dev-activity-report/.env.example \
   ~/.claude/skills/dev-activity-report/.env
```

Edit `.env` with your values (all tunables live here):

```bash
# Where your projects live
APPS_DIR=/home/me/projects

# Additional one-off directories to include
EXTRA_SCAN_DIRS=/usr/local/lib/mydb

# Your name/company for the resume header
RESUME_HEADER=Jane Smith Consulting, Jan 2024 – Present

# Optional: adjust hashing + model picks
ALLOWED_FILE_EXTS=".py,.ts,.js,.tsx,.cs,.csproj,.md,.txt,.json,.toml,.yaml,.yml,.sql,.html,.css,.sh"
PHASE1_MODEL=haiku
PHASE15_MODEL=haiku
PHASE2_MODEL=sonnet
PHASE3_MODEL=gpt-5.1-codex-mini
TOKEN_LOG_PATH=token_economics.log
BUILD_LOG_PATH=build.log
# Subscription auth (leave keys blank when true)
SUBSCRIPTION_MODE=true
```

The Codex/Claude paths and model selections can stay at their defaults unless your setup differs.

---

## Usage

### Run the report

```
/dev-activity-report
```

That's it. Claude reads your `.env`, delegates data gathering to Haiku, synthesizes the report, delegates cache writes to Codex, and saves the output to `~/dev-activity-report-YYYY-MM-DD.md`.

### First run: mark your forks

Before the first run, mark upstream clones you haven't modified so they don't appear as original work:

```bash
# Skip entirely — upstream clone, no original work
touch /path/to/upstream-clone/.not-my-work

# Skip for now — parked, incomplete, or not worth reporting yet
touch /path/to/wip-project/.skip-for-now

# Include as fork — write your contribution notes in the file
echo "- Added custom logging middleware" > /path/to/fork/.forked-work

# Auto-generate contribution notes from git history
touch /path/to/fork/.forked-work-modified
```

For `.forked-work-modified`, the next scan will inspect git log, diffs, and file timestamps to write the `.forked-work` file for you, then delete the trigger.

### Warm scans

Once projects are cached, re-running the skill only re-analyzes projects with new commits or modified files. Typical warm-scan cost is ~$0.031.

---

## File Reference

```
dev-activity-report-skill/
├── SKILL.md                          # Core skill instructions
├── .env.example                      # Config template (copy to .env)
├── .gitignore                        # Ignores .env
└── references/
    ├── token-economics.md            # Cost benchmarks and real test results
    ├── build-history.md              # Design chronicle — how this skill was built
    ├── dev-activity-report-2026-02-13.md    # Example report (v1, pre-ownership markers)
    └── dev-activity-report-2026-02-13-v2.md # Example report (v2, ownership-corrected)
```

Files written to your environment during use:
```
<APPS_DIR>/<project>/.dev-report-cache.md    # Per-project analysis cache
<APPS_DIR>/<project>/.not-my-work            # Ownership marker (you create)
<APPS_DIR>/<project>/.forked-work            # Fork contribution notes
~/.codex/.dev-report-cache.md               # Codex session analytics cache
~/dev-activity-report-YYYY-MM-DD.md         # Report output
```

---

## How It Was Built

This skill was designed and iterated entirely within Claude Code sessions. The `references/build-history.md` file chronicles the full build: 7 milestones from a freeform prompt to a three-phase cache-aware delegation-optimized system, including the discovery that `general-purpose` vs `Bash` subagent type caused a 100x difference in effective token cost.

Key design principles that emerged:

- **Description field as trigger gate** — The SKILL.md `description` is the sole mechanism preventing auto-triggering. Negative constraints matter as much as positive ones.
- **Marker files as lightweight metadata** — `touch .not-my-work` permanently classifies a project. No database, no config file, just a filesystem signal co-located with the code.
- **Auto-documentation via git archaeology** — `.forked-work-modified` demonstrates using AI to eliminate a class of tedious work, triggered by a filesystem event.
- **Agent type matters more than model** — `general-purpose` subagent loaded 618k cache-read tokens per run; `Bash` subagent uses ~5k. The right agent type was a 100x cost optimization.
- **Separate data gathering from synthesis** — Phase 1 collects facts (cheap model, no reasoning). Phase 2 synthesizes (expensive model, reasoning only). Never spend Sonnet tokens on I/O work.
