# Dev Activity Report — ngallodev Software
*Generated: 2026-02-13 (v2 — ownership markers applied)*

---

## Scan Summary

**~/.claude/**: Active Claude Code environment with custom hooks (`permission_request.py`), delegation pipeline (Codex job skill + `delegation-metrics.jsonl`), multi-agent team configs (`builder.md`, `validator.md`), git-tracked config repo, and Claude Code skills system with 9 installed skills.

**/lump/apps/**: 56 directories total. 34 marked `.not-my-work` (excluded). 4 with `.forked-work` (modified forks, included separately). 18 original-work projects.

**/usr/local/lib/mariadb**: Custom MariaDB performance engineering project — dual-mode bulk loading, schema files, pre/post SQL, monitoring scripts. 256GB/28-core server. Last active Jan 2026.

---

## Original Work Projects

| Project | Stack | Last Active |
|---|---|---|
| **invoke-codex-from-claude** | Bash, Python, MCP | Feb 13, 2026 |
| **app-tracker** | .NET 9 Minimal API, EF Core, SQLite, React/Vite, Docker | Feb 13, 2026 |
| **secret-sauce-proj** (RagPipeline) | .NET 9, EF Core, SQLite, Swagger, background channels | Feb 11, 2026 |
| **agentic-workflow** | Python 3.13, FastAPI, Pydantic, pytest | Feb 3, 2026 |
| **osint-framework** | .NET 8, React 18 + TypeScript, Tailwind, MariaDB, Docker, Ollama | Jan 24, 2026 |
| **MariaDB bulk-load toolkit** | SQL, Bash, MariaDB | Jan 19, 2026 |
| **codex-workflows** | Shell, env config | Feb 8, 2026 |
| **anth** | Claude Code skills SDK | Feb 13, 2026 |
| **claude hooks system** (`~/.claude/`) | Python (uv scripts), Bash | Feb 13, 2026 |

---

## Forked & Modified Projects

| Project | Upstream | Original Contributions |
|---|---|---|
| **subgen** | McCloudS/subgen | Designed and implemented `subtitle_cache.py` — persistent JSON cache with thread-safe locking, Docker volume persistence, stale entry cleanup, env-var control. Integrated into startup and post-generation flow. Added `--clear-cache` CLI option, comprehensive test suite, Docker optimization notes. |
| **metube2** | alexta69/metube | Custom Dockerfile with local yt-dlp binary; docker-compose with concurrent download mode + UID/GID config; comprehensive `yt-dlp.conf` (chapter/thumbnail/metadata embedding, NFO writing, auto-subtitle, ban-avoidance sleep, ASCII filenames). |
| **jellyfin-roku** | jellyfin/jellyfin-roku | Tracking upstream feature branch (next-play-like); custom channel poster/splash screen/logo assets across SD/HD/FHD; local deployment against self-hosted Jellyfin. |
| **yt-dlp** | yt-dlp/yt-dlp | Maintained as vendored local build for metube2 Docker integration; kept current through Feb 2026. |

---

## Technical Problems Solved

1. **RAG pipeline architecture (.NET 9)**: Designed and scaffolded a three-layer RAG API (Collection → Document → Chunk) with EF Core + SQLite persistence, background ingestion channel, three service interfaces (chunking, embedding, vector search), and Swagger. Used multi-agent Codex task routing with per-task model selection (mini for mechanical work, max for cross-file wiring).

2. **Multi-agent AI orchestration system**: Designed and codified a human-Claude-Codex pipeline with formal task readiness gates, risk-tier routing (low/medium/high), per-task-type metrics logging, and a learning loop that tightens specs when success rates drop below 70%.

3. **MariaDB bulk-load performance**: Dual-mode configuration system (conservative 68GB buffer pool baseline vs. extreme load mode with safety checks disabled), achieving 50,000–500,000+ rows/second on a 256GB/28-core server. Pre/post SQL scripts, real-time monitoring, CSV/TSV repair utilities.

4. **Subtitle cache for Whisper**: Designed and built a persistent subtitle cache module for the `subgen` fork — thread-safe, Docker-persistent, with auto-cleanup and test coverage — solving startup re-scan overhead on large media libraries.

5. **OSINT intelligence platform**: Full-stack from scratch — .NET 8 API + React 18/TypeScript + Tailwind + MariaDB + Docker + local LLM via Ollama, with pluggable integrations for SpiderFoot, Sherlock, theHarvester.

6. **Claude Code hooks and skills infrastructure**: Custom `permission_request.py` hook for policy-driven tool call auditing; a 9-skill Claude Code skills library including `invoke-codex-from-claude`, `codex-job`, `dev-activity-report`, and team agent roles.

---

## AI-Assisted Development Workflows

- **Parallelized multi-agent task routing**: `secret-sauce-proj` plan explicitly assigns 10 tasks across Codex models (`codex-mini` for mechanical, `codex-max` for cross-file wiring) and Claude (Haiku for smoke tests, Sonnet for review), running in dependency order
- **Codex delegation CLI**: `invoke-codex-from-claude` wraps `codex exec` with push-notification callbacks, structured JSON run logs, verbosity levels, and Claude skill install/uninstall — eliminating manual polling
- **Metrics-driven learning loop**: Global `delegation-metrics.jsonl` tracks every delegated job with cost, duration, model, status, failure class, retry count; rolling 70% success-rate threshold triggers spec tightening
- **`.forked-work-modified` self-documentation**: Novel marker pattern where Claude autonomously inspects git history and file diffs to generate contribution summaries for forked projects, then promotes the marker — no manual writing required
- **`agentic-workflow` framework**: FastAPI + pytest framework built specifically to validate human-AI task orchestration patterns, with `AGENTS.md` role definitions, handoff protocols, and escalation rules

---

## Technology Inventory

**Languages**: C# (.NET 8/9), Python 3.13, TypeScript/JavaScript (React 18), Bash, SQL, BrightScript (Roku)

**Frameworks**: ASP.NET Core Minimal API, EF Core, FastAPI, Pydantic, pytest, React 18, Tailwind CSS, Vite

**AI/LLM**: Claude Code (Sonnet 4.5/Opus), Codex CLI (GPT-5.x models), Ollama (local), MCP protocol, OpenAI API

**Infrastructure**: Docker, Docker Compose, MariaDB (performance-tuned), SQLite, uv, ruff, pnpm

**Tools/Integrations**: Swagger/Swashbuckle, Whisper/faster-whisper, yt-dlp, Jellyfin, Samba, VS Code Server

---

## Timeline

| Period | Work |
|---|---|
| **Feb 2026 (active)** | RAG pipeline API, `invoke-codex-from-claude`, `app-tracker`, Claude skills (`anth`, `dev-activity-report`), `secret-sauce-proj` |
| **Early Feb 2026** | `agentic-workflow` framework, `codex-workflows`, `mcp4kali` stub |
| **Jan 2026** | OSINT framework build, MariaDB bulk-load tuning |
| **Oct–Dec 2025** | OSINT framework inception, media stack (`subgen` fork, `metube2` fork, `jellyfin-roku` fork) |
| **Aug–Sep 2025** | Early tooling experiments (`aitest`, `continue.config`) |

---

## FORMAT A — Resume Bullets

**ngallodev Software, Jan 2025 – Present**

- Architected a .NET 9 RAG pipeline API with multi-layer document/chunk model, EF Core + SQLite persistence, background ingestion channel, and service interface contracts; implemented using a structured multi-agent Codex execution plan with per-task model selection and sequential build verification
- Designed and codified a human-Claude-Codex orchestration system with formal task readiness gates, risk-tiered routing, per-task-type delegation metrics, and a self-tightening spec feedback loop triggered when rolling success rates fall below 70%
- Built `invoke-codex-from-claude`, a Claude skill wrapping `codex exec` with push-notification callbacks, structured JSON run logs, verbosity levels, and one-command install/uninstall — eliminating polling overhead in AI-assisted dev workflows
- Engineered a MariaDB dual-mode bulk loading toolkit achieving 50,000–500,000+ rows/second on a 256GB/28-core server, including automated mode-switching SQL scripts, performance configuration, real-time monitoring, and data repair utilities
- Developed a full-stack OSINT intelligence platform (.NET 8 + React 18/TypeScript + MariaDB + Docker + Ollama) with pluggable integrations for SpiderFoot, Sherlock, and theHarvester, and local LLM-backed analysis
- Extended open-source `subgen` (Whisper subtitle generator) with a persistent, thread-safe subtitle cache module — reducing startup scan time on large media libraries — plus a test suite, Docker volume persistence strategy, and CLI cache management
- Implemented a 9-skill Claude Code skills library and custom Python permission-request hook, establishing a git-tracked, policy-driven AI development environment with builder/validator agent roles and automated delegation telemetry

---

## FORMAT B — LinkedIn Summary Paragraph

Over the past year I've been building at the intersection of software engineering and practical AI orchestration — not just using AI tools, but architecting the workflows that make multi-agent systems reliable and measurable. I designed a human-Claude-Codex delegation pipeline with formal readiness gates, risk routing, and a metrics feedback loop that auto-tightens specs when failure rates spike, and I built the `invoke-codex-from-claude` CLI tooling to operationalize it. On the product side I've built a .NET 9 RAG pipeline API, a full-stack OSINT platform with local LLM integration, and a high-throughput MariaDB bulk-loading toolkit for a 256GB server — alongside meaningful contributions to open-source forks in the self-hosted media space. The through-line is the same everywhere: engineering real systems that happen to use AI, rather than AI demos that happen to look like systems.

---

## Hiring Manager Highlights (Top 3)

**1. The delegation metrics + self-tightening learning loop**
A global `delegation-metrics.jsonl` tracks every Codex job — model, cost, duration, status, failure class, retry count. Every 10 jobs per task type, rolling success rate is computed; if it drops below 70%, specs tighten automatically. This is not "I use AI" — this is building operational infrastructure *around* AI to make it reliable at scale. Extremely rare thinking.

**2. The `.forked-work-modified` autonomous documentation pattern**
A novel marker file convention where dropping a single empty file in a forked repo directory causes Claude to autonomously inspect git history, diffs, and timestamps to generate a contribution summary — then promote the marker. This is a small but genuinely creative human-AI workflow invention: using AI to eliminate a class of tedious documentation work, triggered by a filesystem signal. It demonstrates both systems thinking and practical AI integration instincts.

**3. RAG pipeline with structured multi-agent task routing**
The `secret-sauce-proj` plan assigns each scaffold task to a specific Codex model tier (`codex-mini` for mechanical/deterministic work, `codex-max` for cross-file wiring), with Claude Haiku for smoke testing and Claude Sonnet for code review — all in documented execution order with build verification gates between tasks. This is mature thinking about AI cost/capability tradeoffs applied to real engineering work.
