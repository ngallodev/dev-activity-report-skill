# Go-Live Multi-Agent Execution Plan

Date: 2026-02-17
Author: Codex (GPT-5)
Scope: Resolve pre-go-live blockers from planning-docs/PLAN.md with quality preserved and low LLM wall-time.

## Critical Findings From Plan Review

1. Phase 1 cache instability risk: fingerprint currently includes volatile telemetry from `~/.claude` and `~/.codex`, causing avoidable invalidations.
2. `--since` needs baseline replacement logic, not additive filtering on top of `HEAD~20`.
3. Interactive mode must remain optional and non-blocking for automation paths.
4. Multi-root support requires cache schema/versioning safeguards.
5. Benchmarking must enforce explicit cold/warm gates tied to existing benchmark logs.

## Design Principles

- Prefer deterministic Python scripts and local transforms over extra model calls.
- Keep LLM usage concentrated in existing synthesis phase only.
- Preserve backward compatibility and automation defaults.
- Implement with staged test gates and measurable performance checks.

## Workstreams and Agent Ownership

### Agent A: Core CLI + Cache Semantics
Files:
- `skills/dev-activity-report-skill/scripts/phase1_runner.py`
- `skills/dev-activity-report-skill/scripts/run_pipeline.py`
- `skills/dev-activity-report-skill/scripts/run_report.sh`

Deliverables:
- Add CLI/env support for `--since`, `--refresh`, and repeatable scan roots.
- Refactor fingerprint policy for stable caching under unchanged project state.
- Add cache versioning/migration-safe reads.

### Agent B: Installer + Operational UX
Files:
- `skills/dev-activity-report-skill/scripts/` (installer entry)
- `README.md`

Deliverables:
- One-command Python installer with idempotent sync behavior.
- Prereq checks (`claude`, Python runtime/deps), setup invocation, and clear failures.

### Agent C: Interactive Review Mode
Files:
- `skills/dev-activity-report-skill/scripts/review_report.py`
- `skills/dev-activity-report-skill/scripts/run_pipeline.py`

Deliverables:
- JSON-first bullet review/edit/prune flow before render.
- `--interactive` flag that is fully bypassable for CI/default runs.

### Agent D: Tests + Benchmarks
Files:
- `tests/test_pipeline_contracts.py`
- `tests/test_caching_integrity.py`
- `tests/test_non_git_handling.py`
- `tests/test_render_output.py`
- benchmark hooks under scripts if needed

Deliverables:
- Coverage for `--since`, `--refresh`, multi-root cache isolation, interactive bypass.
- Cold/warm benchmark capture and regression checks.

### Agent E: Documentation + Release Log
Files:
- `README.md`
- `planning-docs/PLAN.md`
- `build-history.md`

Deliverables:
- Updated usage docs and limitations notes.
- Build-history append-only milestone with benchmark evidence and migration notes.

## Execution Order

1. Run Agent A and Agent D in parallel to lock behavior + tests.
2. Run Agent B and Agent C in parallel once CLI contracts stabilize.
3. Run Agent E after implementation and benchmark numbers are available.
4. Integrate, run full suite in `tests/`, capture benchmark results, finalize.

## Quality Gates

- Full test suite passes.
- Default non-interactive flow remains unchanged.
- Cache behavior is deterministic across window/root/refresh changes.
- Benchmarks logged with explicit cold/warm deltas.
- Build history updated with meaningful descriptive entry.

## Cost/Latency Controls

- Avoid new model prompts in feature paths where deterministic code suffices.
- Reuse compact payloads and existing cache checkpoints.
- Keep benchmark/test loops targeted until final full-suite run.
