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
prompt: (see below)
```

Prompt to send (substitute all ${VAR} values before sending):

```
You are a data collection agent. Run the following bash commands exactly and return ALL output verbatim with section headers. Do not interpret, summarize, or omit anything.

=== SECTION: OWNERSHIP MARKERS ===
find ${APPS_DIR} -maxdepth 2 \( -name ".not-my-work" -o -name ".forked-work" -o -name ".forked-work-modified" -o -name ".skip-for-now" \) | sort

=== SECTION: CACHE FINGERPRINTS ===
python3 - << 'PYEOF'
import os, subprocess

apps_dir = '${APPS_DIR}'

def dir_fp(d):
    """Git hash for git repos; max mtime of content files (excluding .dev-report-cache.md) for non-git dirs."""
    r = subprocess.run(['git','-C',d,'rev-parse','HEAD'], capture_output=True, text=True)
    if r.returncode == 0: return r.stdout.strip()
    result = subprocess.run(
        f'find {d} -maxdepth 3 -not -name ".dev-report-cache.md" -not -path "*/.git/*" -type f -printf "%T@\\n" 2>/dev/null | sort -n | tail -1',
        shell=True, capture_output=True, text=True)
    mt = result.stdout.strip().split('.')[0] if result.stdout.strip() else ''
    return mt or subprocess.check_output(['stat','-c','%Y',d]).decode().strip()

skip = set()
for marker in ['.not-my-work', '.skip-for-now']:
    for f in subprocess.check_output(f"find {apps_dir} -maxdepth 2 -name '{marker}'", shell=True, text=True).splitlines():
        skip.add(f.replace(f'/{marker}',''))
for name in sorted(os.listdir(apps_dir)):
    d = f'{apps_dir}/{name}'
    if not os.path.isdir(d) or d in skip: continue
    fp = dir_fp(d)
    cache = subprocess.run(['head','-2',f'{d}/.dev-report-cache.md'], capture_output=True, text=True).stdout.strip()
    print(f'{d} | {fp} | {cache}')
PYEOF

=== SECTION: STALE PROJECT FACTS ===
python3 - << 'PYEOF'
import os, subprocess

apps_dir = '${APPS_DIR}'

def read(path, lines=50):
    try:
        with open(path) as f: return ''.join(f.readlines()[:lines]).strip()
    except: return ''

def dir_fp(d):
    r = subprocess.run(['git','-C',d,'rev-parse','HEAD'], capture_output=True, text=True)
    if r.returncode == 0: return r.stdout.strip()
    result = subprocess.run(
        f'find {d} -maxdepth 3 -not -name ".dev-report-cache.md" -not -path "*/.git/*" -type f -printf "%T@\\n" 2>/dev/null | sort -n | tail -1',
        shell=True, capture_output=True, text=True)
    mt = result.stdout.strip().split('.')[0] if result.stdout.strip() else ''
    return mt or subprocess.check_output(['stat','-c','%Y',d]).decode().strip()

skip = set()
for marker in ['.not-my-work', '.skip-for-now']:
    for f in subprocess.check_output(f"find {apps_dir} -maxdepth 2 -name '{marker}'", shell=True, text=True).splitlines():
        skip.add(f.replace(f'/{marker}',''))

for name in sorted(os.listdir(apps_dir)):
    d = f'{apps_dir}/{name}'
    if not os.path.isdir(d) or d in skip: continue
    fp = dir_fp(d)
    cache_hdr = subprocess.run(['head','-1',f'{d}/.dev-report-cache.md'], capture_output=True, text=True).stdout.strip()
    if fp and cache_hdr and fp in cache_hdr: continue  # cache hit — skip
    print(f'\n--- PROJECT: {name} ---')
    print(f'MTIME: {subprocess.check_output(["stat","-c","%y",d]).decode().strip()}')
    gl = subprocess.run(['git','-C',d,'log','--oneline','-10'], capture_output=True, text=True).stdout.strip()
    if gl: print(f'GIT LOG:\n{gl}')
    files = subprocess.run(
        f'find {d} -maxdepth 3 -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/venv/*" -not -path "*/bin/*" -not -path "*/obj/*" -type f \\( -name "*.md" -o -name "*.csproj" -o -name "Dockerfile*" -o -name "docker-compose*.yml" \\) 2>/dev/null | head -20',
        shell=True, capture_output=True, text=True).stdout.strip()
    if files: print(f'KEY FILES:\n{files}')
    # Also collect any Codex-related files in this project dir
    codex_files = subprocess.run(
        f'find {d} -maxdepth 3 -not -path "*/.git/*" -type f \\( -name "AGENTS.md" -o -name "codex.md" -o -name ".codex" \\) 2>/dev/null | head -10',
        shell=True, capture_output=True, text=True).stdout.strip()
    if codex_files: print(f'CODEX FILES:\n{codex_files}')
    for fname in ['README.md','AGENTS.md','.claude/plan.md','.forked-work']:
        content = read(f'{d}/{fname}')
        if content: print(f'\n{fname}:\n{content[:800]}')
PYEOF

=== SECTION: FORKED-WORK-MODIFIED ===
find ${APPS_DIR} -maxdepth 2 -name ".forked-work-modified" | sed 's|/.forked-work-modified||'
# Note: .skip-for-now dirs are excluded from forked-work-modified processing too (they won't appear here since find won't descend into them from the stale facts section)
# For each found, also run:
# git -C <dir> log --oneline -20
# git -C <dir> diff HEAD~10..HEAD --name-only
# find <dir> -maxdepth 2 -newer <dir>/README.md -not -path '*/.git/*' -type f 2>/dev/null | head -20

=== SECTION: EXTRA FIXED LOCATIONS ===
python3 - << 'PYEOF'
import os, subprocess

extra_dirs = '${EXTRA_SCAN_DIRS}'.split()

def read(path, lines=30):
    try:
        with open(path) as f: return ''.join(f.readlines()[:lines]).strip()
    except: return ''

def dir_fp(d):
    r = subprocess.run(['git','-C',d,'rev-parse','HEAD'], capture_output=True, text=True)
    if r.returncode == 0: return r.stdout.strip()
    result = subprocess.run(
        f'find {d} -maxdepth 3 -not -name ".dev-report-cache.md" -not -path "*/.git/*" -type f -printf "%T@\\n" 2>/dev/null | sort -n | tail -1',
        shell=True, capture_output=True, text=True)
    mt = result.stdout.strip().split('.')[0] if result.stdout.strip() else ''
    return mt or subprocess.check_output(['stat','-c','%Y',d]).decode().strip()

for d in extra_dirs:
    d = os.path.expanduser(d)
    if not os.path.isdir(d): continue
    fp = dir_fp(d)
    cache_hdr = subprocess.run(['head','-1',f'{d}/.dev-report-cache.md'], capture_output=True, text=True).stdout.strip()
    if fp and cache_hdr and fp in cache_hdr:
        print(f'CACHE HIT: {d}')
        print(subprocess.run(['cat',f'{d}/.dev-report-cache.md'], capture_output=True, text=True).stdout.strip())
        continue
    print(f'\n--- EXTRA: {d} ---')
    print(f'MTIME: {subprocess.check_output(["stat","-c","%y",d]).decode().strip()}')
    gl = subprocess.run(['git','-C',d,'log','--oneline','-10'], capture_output=True, text=True).stdout.strip()
    if gl: print(f'GIT LOG:\n{gl}')
    for fname in ['README.md','AGENTS.md','.forked-work']:
        content = read(f'{d}/{fname}')
        if content: print(f'\n{fname}:\n{content[:600]}')
PYEOF

=== SECTION: CLAUDE ACTIVITY ===
ls ${CLAUDE_HOME}/skills/ 2>/dev/null
ls ${CLAUDE_HOME}/hooks/ 2>/dev/null
ls ${CLAUDE_HOME}/agents/team/ 2>/dev/null
head -2 ${CLAUDE_HOME}/delegation-metrics.jsonl 2>/dev/null

=== SECTION: INSIGHTS LOG ===
tail -60 ${SKILL_DIR}/references/insights/insights-log.md 2>/dev/null || echo "No insights log found"

=== SECTION: CODEX ACTIVITY ===
python3 - << 'PYEOF'
import os, subprocess, json, glob

codex_home = os.path.expanduser('${CODEX_HOME}')
cache_path = os.path.join(codex_home, '.dev-report-cache.md')

# Fingerprint: mtime of sessions directory
sessions_dir = os.path.join(codex_home, 'sessions')
try:
    fp = subprocess.check_output(['stat','-c','%Y', sessions_dir]).decode().strip()
except:
    fp = 'unknown'

cache_hdr = subprocess.run(['head','-1', cache_path], capture_output=True, text=True).stdout.strip()
if fp and cache_hdr and fp in cache_hdr:
    print('CODEX CACHE HIT')
    print(open(cache_path).read())
else:
    print(f'CODEX FINGERPRINT: {fp}')

    # config.toml — model, trusted projects
    cfg = os.path.join(codex_home, 'config.toml')
    if os.path.exists(cfg):
        print(f'\nCODEX CONFIG:\n{open(cfg).read()[:1000]}')

    # skills
    skills_dir = os.path.join(codex_home, 'skills')
    if os.path.isdir(skills_dir):
        skill_names = [d for d in os.listdir(skills_dir) if not d.startswith('.')]
        print(f'\nCODEX SKILLS: {", ".join(sorted(skill_names))}')

    # session rollup: count sessions per month, collect unique cwds, gather recent task summaries
    if os.path.isdir(sessions_dir):
        session_files = sorted(glob.glob(os.path.join(sessions_dir, '**', '*.jsonl'), recursive=True))
        months = {}
        cwds = set()
        recent_tasks = []
        for sf in session_files[-50:]:  # last 50 session files only to bound I/O
            try:
                month = sf.split('/')[-4] + '-' + sf.split('/')[-3]  # YYYY/MM -> YYYY-MM
                months[month] = months.get(month, 0) + 1
                with open(sf) as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            # extract cwd from session_meta
                            if obj.get('type') == 'session_meta':
                                cwd = obj.get('payload', {}).get('git', {})
                                # cwd is in environment_context messages
                            if obj.get('type') == 'response_item':
                                for c in obj.get('payload', {}).get('content', []):
                                    if isinstance(c, dict) and 'environment_context' in c.get('text',''):
                                        import re
                                        m = re.search(r'<cwd>(.*?)</cwd>', c.get('text',''))
                                        if m: cwds.add(m.group(1))
                        except: pass
            except: pass
        print(f'\nCODEX SESSIONS BY MONTH: {dict(sorted(months.items()))}')
        if cwds: print(f'CODEX ACTIVE CWDS: {", ".join(sorted(cwds))}')

    # rules summary
    rules_file = os.path.join(codex_home, 'rules', 'default.rules')
    if os.path.exists(rules_file):
        lines = open(rules_file).readlines()
        print(f'\nCODEX RULES COUNT: {len(lines)} entries')
PYEOF
```

Wait for the subagent to return all output before proceeding.

### 1b. Process `.forked-work-modified` (if any found in SECTION: FORKED-WORK-MODIFIED)

For each directory listed, use the git log/diff/file data returned by the subagent to write a concise `.forked-work` summary (3-6 bullets) directly, then delete the `.forked-work-modified` marker. Do this yourself — it requires judgment.

---

## Phase 2 — Analysis (synthesize from gathered facts only)

Using only the data collected in Phase 1 (do not re-read any files), produce:

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
