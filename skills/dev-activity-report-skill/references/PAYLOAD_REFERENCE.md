# Payload Reference (compact keys)

| Key | Meaning | Notes / Examples |
|---|---|---|
| `ts` | Timestamp (UTC ISO) when Phase 1 ran | `"2026-02-15T10:00:00Z"` |
| `ad` | Apps directory scanned | `"~/projects"` |
| `mk` | Ownership markers | List of objects: `{ "m": ".forked-work", "p": "invoke-codex" }` |
| `p` | Stale projects needing analysis | List of project objects (below) |
| `x` | Extra fixed locations summary | List of `{ "p": "<path>", "fp": "<hash>", "git": bool, "kf": ["README.md", ...], "exists": bool }` |
| `cl` | Claude home snapshot | `{ "sk": ["skill-a"], "hk": ["hook-a"], "ag": ["team/default"] }` |
| `cx` | Codex home snapshot | `{ "sm": {"2026-02": 4}, "cw": ["~/projects/foo"], "sk": ["dev-activity-report"] }` |
| `ins` | Tail of `references/insights/insights-log.md` (up to 24 lines) | Used for AI workflow patterns |
| `stats` | Counts for bookkeeping | `{ "total": 12, "stale": 3, "cached": 9 }` |

## Project object (`p` entries)

| Key | Meaning | Example |
|---|---|---|
| `n` | Project name | `"invoke-codex-from-claude"` |
| `pt` | Absolute path | `"~/projects/invoke-codex-from-claude"` |
| `fp` | Content-based fingerprint of git-tracked files (or allowed non-git files) | `"a1b2c3..."` |
| `st` | Status derived from markers | `orig` (default), `fork`, `fork_mod`, `skip`, `not` |
| `cc` | Commits since last cached fingerprint (best-effort) | `5` |
| `sd` | `git diff --shortstat <base>..HEAD` | `"4 files changed, 120 insertions(+), 12 deletions(-)"` |
| `fc` | Changed file list (trimmed) | `["src/main.py","README.md"]` |
| `msg` | Recent commit subjects (trimmed) | `["refactor draft executor","fix retry jitter"]` |
| `hl` | Derived themes for fast reasoning | `["perf","ai-workflow","deps"]` |

## Marker values

- `.not-my-work` → status `not` (ignored)
- `.skip-for-now` → status `skip` (ignored)
- `.forked-work` → status `fork`
- `.forked-work-modified` → status `fork_mod`
- none → status `orig`

The payload omits cached projects to reduce token load; Phase 2 only needs stale entries plus the marker list for context.
