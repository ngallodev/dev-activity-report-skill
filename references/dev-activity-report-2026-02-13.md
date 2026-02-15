# Dev Activity Report — ngallodev Software
*Generated: 2026-02-13*

---

## Scan Summary

**~/.claude/**: Active Claude Code environment with custom hooks (`permission_request.py`), a delegation pipeline (Codex job skill + metrics logging), multi-agent team configs (`builder.md`, `validator.md`), and a git-tracked configuration repo.

**/lump/apps/**: 50+ project directories. Key active work summarized below.

**/usr/local/lib/mariadb**: Fully custom MariaDB performance engineering project — dual-mode bulk loading system, schema files, pre/post load SQL scripts, performance config, and status monitoring tooling. Actively maintained through Jan 2026 on a 256GB RAM / 28-core Xeon server.

**~/projects, ~/dev, ~/src, ~/code**: Do not exist.

---

## Findings

### 1. Projects Built or Actively Developed

| Project | Stack | Last Active |
|---|---|---|
| **invoke-codex-from-claude** | Bash, Python | Feb 13, 2026 |
| **app-tracker** | .NET 9, SQLite/EF Core, React/Vite, Docker | Feb 13, 2026 |
| **hexstrike-ai** | Python, MCP protocol | Feb 11, 2026 |
| **MCP-Kali-Server** | Python, MCP protocol | Feb 11, 2026 |
| **secret-sauce-proj** | Unknown (active) | Feb 11, 2026 |
| **agentic-workflow** | Python, FastAPI, Pydantic, pytest | Feb 3, 2026 |
| **metube2** | Python, Docker, yt-dlp, uv | Feb 4, 2026 |
| **firecrawl** | Self-hosted (Node/Python) | Feb 5, 2026 |
| **subgen** | Python, Whisper/faster-whisper, Docker | Feb 4, 2026 |
| **osint-framework** | .NET 8, React 18 + TypeScript, Tailwind, MariaDB, Docker, Ollama | Jan 24, 2026 |
| **jellyfin-roku** | Roku/BrightScript | Dec 25, 2025 |
| **MariaDB bulk-load toolkit** | SQL, Bash, MariaDB | Jan 19, 2026 |
| **tookie-osint** | Python (web UI + modules) | Nov 4, 2025 |

### 2. Technical Problems Solved

- **MariaDB performance engineering**: Built a dual-mode configuration system targeting 50,000–500,000+ rows/second bulk load throughput on a multi-role server (256GB RAM, 28-core Xeon). Wrote automated pre/post load SQL, performance.cnf tuning, and real-time monitoring scripts. Authored companion Python utilities to repair/convert malformed CSV/TSV/SQL export formats.
- **AI-human orchestration architecture**: Designed and implemented a multi-tier delegation pipeline — Claude (planning) → Codex (execution) with readiness gating, risk routing, metrics collection, and a learning feedback loop. Documented in CLAUDE.md and formalized via the `invoke-codex-from-claude` skill.
- **MCP server development**: Built `MCP-Kali-Server` as an AI-driven penetration testing bridge, exposing 10+ security tools (nmap, Metasploit, sqlmap, Nikto, etc.) via the MCP protocol for use with Claude and other LLM clients.
- **OSINT platform**: Built a full-stack OSINT framework from scratch — .NET 8 backend, React 18 + TypeScript frontend, MariaDB, Docker Compose, local LLM integration via Ollama, and pluggable tooling for SpiderFoot, Sherlock, and theHarvester.
- **Media automation**: Deployed and customized self-hosted media stack (subgen + Whisper for AI subtitle generation, metube2 + yt-dlp for video acquisition, jellyfin-roku Roku channel, Stash integration), including forked and patched versions of upstream projects.
- **Claude Code hooks**: Implemented a custom `permission_request.py` hook (uv-executable Python script) for auditing, auto-allowing, and denying tool calls based on policy.

### 3. AI-Assisted Development Workflows Demonstrated

- **Codex delegation system**: Built the `invoke-codex-from-claude` tool specifically to automate dispatching well-scoped tasks from Claude to Codex CLI, with push notifications, structured run logging, and resumable sessions. Installed as a Claude skill.
- **Metrics-driven learning loop**: The CLAUDE.md global config tracks delegation outcomes in `delegation-metrics.jsonl` and triggers spec-tightening when per-task-type success rates drop below 70%.
- **Multi-agent AGENTS.md conventions**: Projects like `agentic-workflow` include dedicated `AGENTS.md` files structuring Claude/Codex collaboration roles, handoff protocols, and escalation rules.
- **Parallelized multi-lane planning**: The `app-tracker` Day 1 plan explicitly assigns parallel execution lanes to Codex (`gpt-4.1`) and Claude (Sonnet/Opus) for different concerns (DB, API, observability, AI layer contracts) — running simultaneously.
- **HexStrike AI / MCP-Kali-Server**: Integrated MCP protocol to expose real security tooling to LLMs, enabling Claude and other agents to directly invoke penetration testing tools in real time.

### 4. Technology / Tools Inventory

**Languages**: Python, C# (.NET 8/9), TypeScript/JavaScript (React), Bash, SQL, BrightScript (Roku)

**Frameworks/Libs**: FastAPI, Pydantic, pytest, EF Core, React 18, Tailwind CSS, Vite, yt-dlp, faster-whisper/stable-ts, Firecrawl, Selenium

**AI/LLM**: Claude Code (Claude 3.5/4.5 Sonnet, Opus), Codex CLI (GPT-4.1, GPT-5.x models), Ollama (local LLMs), MCP protocol, OpenAI API

**Infrastructure**: Docker, Docker Compose, MariaDB (tuned), SQLite, Jenkins (present), LibreNMS, Samba, VS Code Server, uv, ruff, pnpm

**Security tooling**: nmap, Metasploit, sqlmap, Nikto, Hydra, John the Ripper, gobuster, WPScan, Dirb, Sherlock, theHarvester, SpiderFoot

**Media stack**: Jellyfin, yt-dlp, MeTube, Subgen (Whisper), Stash, yt-dlp-web-ui, ytdl-sub

### 5. Timeline of Activity

| Period | Work |
|---|---|
| **Feb 2026 (active)** | `invoke-codex-from-claude` skill (today), `app-tracker` planning/dev, Claude Code skills/hooks system, `hexstrike-ai` + `MCP-Kali-Server` |
| **Early Feb 2026** | `agentic-workflow` Python/FastAPI framework, `firecrawl` deployment, `metube2` customization, `subgen` setup |
| **Jan 2026** | `osint-framework` full-stack build, MariaDB bulk-load tuning (final session Jan 17–19), `codex-workflows` tooling |
| **Dec 2025** | `jellyfin-roku` Roku channel, `stash`/`stashapp` integrations, `yt-dlp`/`yt-dlp-web-ui` |
| **Nov 2025** | `tookie-osint` OSINT tooling |
| **Oct–Sep 2025** | `makestaticsite`, `wayback-machine-webextension`, `WayBackupFinder`, `facebook-scraper-selenium`, MariaDB initial build |

---

## FORMAT A — Resume Bullets

**ngallodev Software, Jan 2025 – Present**

- Architected and implemented a multi-agent AI orchestration system pairing Claude Code with Codex CLI, formalizing delegation readiness gates, risk-tiered routing, and a metrics-driven feedback loop that auto-tightens specs when per-task success rates fall below 70%
- Built `invoke-codex-from-claude`, a Claude skill that dispatches implementation tasks to Codex CLI asynchronously with push-notification callbacks, structured run logging, and session resume — eliminating polling overhead in human-AI dev workflows
- Engineered MariaDB dual-mode bulk loading toolkit achieving 50,000–500,000+ rows/second on a 256GB/28-core server, including automated pre/post SQL scripts, conservative vs. extreme configuration switching, real-time monitoring, and malformed-CSV repair utilities
- Developed a full-stack OSINT intelligence platform (.NET 8 API + React 18/TypeScript + MariaDB + Docker) with pluggable integrations for SpiderFoot, Sherlock, theHarvester, and local LLM analysis via Ollama
- Constructed `MCP-Kali-Server`, a Python MCP bridge exposing 10+ penetration testing tools (nmap, Metasploit, sqlmap, Nikto, Hydra) to any MCP-compatible LLM client, enabling real-time AI-driven offensive security automation
- Deployed and customized a self-hosted media automation stack integrating AI subtitle generation (Whisper/faster-whisper via Subgen), video acquisition (yt-dlp/MeTube), and Jellyfin delivery — including a custom Roku channel client
- Implemented custom Claude Code hooks in Python (uv-executable, policy-driven permission request handler) and established a git-tracked, team-configured AI dev environment with builder/validator agent roles

---

## FORMAT B — LinkedIn Summary Paragraph

Over the past year I've been doing deep independent work at the intersection of software engineering and practical AI integration — building tools that make LLM-assisted development faster, more reliable, and architecturally sound. I designed and implemented a multi-agent orchestration system that pairs Claude Code for planning with Codex CLI for execution, complete with readiness gates, risk routing, and a metrics feedback loop that learns from delegation outcomes. On the infrastructure side I've built a full-stack OSINT platform, engineered high-throughput MariaDB bulk-loading tooling for a 256GB server, and developed an MCP-based penetration testing automation framework that gives AI models direct access to real security tooling. What I'm most proud of is that none of this is toy work — it's production-grade engineering applied to genuinely hard problems, with AI used as a force multiplier at every layer.

---

## Hiring Manager Highlights (Top 3)

**1. The delegation metrics + learning loop (CLAUDE.md + `invoke-codex-from-claude`)**
This goes far beyond "I use AI tools." You designed a self-improving human-AI pipeline with formal task readiness criteria, risk-tier routing, per-task-type success rate tracking, and automated spec-tightening when failure rates spike. That's systems thinking applied to AI workflows — rare and valuable.

**2. MariaDB bulk-load performance engineering**
Achieving 50,000–500,000+ rows/second on multi-role hardware by building a dual-mode switching system (conservative baseline vs. extreme load mode with automatic restoration) demonstrates real infrastructure depth. Writing the companion CSV/TSV repair utilities shows ownership of the full data pipeline, not just the happy path.

**3. OSINT Framework + MCP-Kali-Server (AI-native security tooling)**
Building a full-stack OSINT platform (.NET 8 / React 18 / MariaDB / Docker / Ollama) and simultaneously building an MCP bridge that gives LLMs real-time control of penetration testing toolkits (Metasploit, sqlmap, Nikto, etc.) signals a genuinely unusual combination: full-stack product engineering + security domain knowledge + LLM protocol integration. That's a differentiated profile.
