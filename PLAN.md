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
