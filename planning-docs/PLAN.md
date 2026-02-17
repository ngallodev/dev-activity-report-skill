Single-Machine Limitation: As noted in your roadmap, being tied to a single local machine is the biggest functional limitation. For developers working across multiple workstations (laptop, desktop) or wanting to generate reports for past roles, this is a blocker.

No Time-Based Scoping (--since): This is another key limitation from your roadmap. The ability to generate reports for a specific date range (e.g., "last quarter," "during my internship") is crucial for creating targeted resumes or updates. This should be a high-priority feature.

Lack of a --refresh Flag: Manually deleting cache files is a friction point for power users who want to force a fresh scan. Implementing this flag (as planned) will improve usability.

Complex Setup & Dependencies: The installation, while documented, is not trivial. It requires understanding Claude Code, skills, sandboxes, and multiple configuration files. This might deter less technical users. A one-command installer script could lower the barrier to entry.

UI/UX is Report-Centric: The "user interface" is the generated markdown/HTML reports. While functional, the tool lacks an interactive component for previewing, editing, or selecting which activities to include before final output. This could be a future evolution.

and here are the suggested changes, in order of priority before we can "ship it!": Implement --since <date>: This is the most critical feature for real-world resume/update use. It unlocks the tool's primary value proposition.

Create a One-Command Installer: A simple shell script (curl | sh) or a Python script that handles cloning, copying files, and prompting for initial .env setup would dramatically improve adoption.

Add --refresh Flag: Implement this as planned to give users an easy escape hatch from caching.

Explore Multi-Machine Support: Start by adding support for a user-specified list of directories that could be on remote mounts or synced folders (like Dropbox). Full SSH support is a bigger lift.

Consider Interactive Mode: A simple CLI menu after the report is generated could let users select which bullet points to keep, edit them, and then export. This adds a layer of polish and control.

## Notes

- **Touchpoints**: `README.md`, `skills/dev-activity-report-skill/scripts/run_pipeline.py`, and `skills/dev-activity-report-skill/scripts/phase1_runner.py` are the primary files to coordinate for these updates, so align CLI args, Phase 1 data gathering, and documentation modifications.
- **Multi-machine**: Phase 1 currently iterates only `APPS_DIR` (extra scan dirs are treated as summaries), so supporting multiple roots requires looping each configured path, expanding the fingerprint/cache metadata per root, and ensuring caches stay tied to their origin locations.
- **--since**: No CLI flag or git helper honors a date range today; add a `--since` argument (and/or env equivalent) that flows into every git stat/shortstat/changed-files helper and becomes part of the fingerprint so cached run results reflect the requested window.
- **--refresh**: The current cache check (`read_cache()` in `phase1_runner.py`) always reuses `.phase1-cache.json`; a refresh flag should skip the cache read (and optionally delete it) to force Phase 1 to rebuild per-project summaries and rewrite `.dev-report-cache.md`.
- **Installer**: Installation still means manual clone/copy plus `scripts/setup_env.py`, so the installer should clone/pull the repo, copy/sync the skill into `~/.claude/skills/`, run the env setup workflow, and verify prerequisites like the `claude` CLI binary.
- **Interactive mode**: `render_report.py` renders deterministic Markdown/HTML today; add an interactive review step that reads the Phase 2 JSON, lets the user edit/prune bullets via a CLI menu, and feeds the curated data into the renderer before exporting.
