for all agents, codex, claude, gemini, etc.:

<skill definition>
A skill is a folder containing:
• SKILL.md (required): Instructions in Markdown with YAML frontmatter
• scripts/ (optional): Executable code (Python, Bash, etc.)
• references/ (optional): Documentation loaded as needed
• assets/ (optional): Templates, fonts, icons used in output
</skill definition>

<project-structure-definition>
    {project-root}/
    README.md
    CLAUDE.md
    AGENTS.md (link)
    build-history.md
    planning-docs/
        PLAN.md
        PROGRESS.md
    skills/
        dev-activity-report-skill/
            SKILL.md
            references/
                examples/
                    .env.example
                    insights/
                        insights-log.md
                token-economics.md
            scripts/
                phase1_runner.py
                testing/
                    run_codex_test_report.sh
            assets/
</project-structure-definition>

do not change the basic project structure.
do not remove any files unless explicitly asked.
do not add any new files unless explicitly asked.
all scripts live in or under  <project-root>skills/dev-activity-report-skill/scripts/
all planning docs live in <project-root>/planning-docs/
all references live in <project-root>skills/dev-activity-report-skill/references/

In all actions and changes:
  - optimize for token usage efficiency.
  - The time it takes to finish the task does not matter.
  - The only exception to this is in phase two
     -analysis
     -synthesis
     -report generation
     -in these phases you should use the best model for the job - smart, creative, and thoughtful.

update and document build-history.md with the latest changes, be descriptive.
benchmark your changes, and benchmark any test runs.  make sure benchmarks are tracked in the appropriate place.
