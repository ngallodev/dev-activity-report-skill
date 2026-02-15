## Optimization Plan

1. **Phase 1 short-circuiting**  
   - Introduce a lightweight fingerprint that summarizes the entire scan state (projects tracked, ownership markers, Codex sessions) and store the last Phase 1 payload.  
   - Before launching the Haiku subagent, compute the current fingerprint and skip Phase 1 if it matches the cached value, reusing the previously saved structured output.  

2. **Lean Phase 1 payload**  
   - Refactor the Phase 1 script so each section emits structured (JSON-like) data with explicit field limits instead of human-readable headers and verbatim command output.  
   - Trim git logs/README snippets to only what Claude needs, and discard noisy `find` listings or long file dumps.  

3. **Suppress noisy terminal output**
   - Route command stderr to `/dev/null` where permission warnings occur and remove decorative banners so the skill writes only the structured payload to stdout.
   - Keep the downstream Phase 2 prompt unchanged (no trimming of Sonnet output) since expanding its output is a later phase.

---

## TODO (from PR #2 review)

4. **`run_report.sh` — remove hardcoded absolute paths**
   - `ROOT_DIR`, `SKILL_DIR`, and `CODEX_BIN` are all hardcoded to `/lump/apps/...` and `/home/nate/.nvm/...`.
   - Derive `ROOT_DIR` from `$0` (e.g. `$(cd "$(dirname "$0")/../../../" && pwd)`) and `CODEX_BIN` from `command -v codex` with a clear error if not found.
   - Makes the runner usable after the skill is installed to `~/.claude/skills/`.

5. **`run_report.sh` — remove silent `sudo apt-get install` in `notify_done`**
   - The current fallback runs `sudo apt-get update && apt-get install -y libnotify-bin` silently, which is surprising and requires elevated privileges.
   - Replace with: print a one-line message to stderr explaining how to install `libnotify-bin`, then exit 0 (don't hard-fail the whole run just because desktop notifications are unavailable).
