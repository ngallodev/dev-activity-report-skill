High – benchmark logging uses wrong total: record_benchmark builds timings_sec from the dictionary that already contains total and
    then sets total_sec = sum(timings.values()), so the logged total_sec value is roughly total + total and the benchmark file records
    inflated totals that won’t match the actual runtime. Drop total before summing or explicitly sum only the phase durations (phase1,
    phase1.5, phase2, phase3) so the benchmark record reflects the real run time. (skills/dev-activity-report-skill/scripts/
    run_pipeline.py:263-287)

     High: run_pipeline.py passes --tools "" to the claude CLI. If the CLI treats an empty string as an invalid tool name, Phase 1.5/2 will fail
    immediately. Suggest removing --tools entirely or supplying the correct explicit value supported by the CLI. skills/dev-activity-report-skill/
    scripts/run_pipeline.py:96
  - Medium: claude_call() hard-codes timeout=120. Phase 2 prompts can exceed 120s and will fail even when the CLI is still working. Consider making
    this configurable via .env or bumping the default. skills/dev-activity-report-skill/scripts/run_pipeline.py:107
  - Medium: When Phase 1 doesn’t emit JSON, the pipeline falls back to reading .phase1-cache.json, but then assumes fp/cache_hit keys. Cached
    entries use fingerprint and omit cache_hit, so logs/benchmarks mislabel warm runs as cold and show fp as n/a. Normalize the cached shape before
    use. skills/dev-activity-report-skill/scripts/run_pipeline.py:369 skills/dev-activity-report-skill/scripts/run_pipeline.py:380
  - Medium: The fingerprint ignore list contains a global *.txt, which will ignore any .txt in any repo and can mask real changes, leading to false
    cache hits. Consider narrowing to debug/*.txt (or a specific path) instead of a global suffix. skills/dev-activity-report-skill/.dev-report-
    fingerprint-ignore:27
  - Low: clear_cache.py’s expand() only expands ~ and not env vars (e.g., $HOME). If APPS_DIR is set with $HOME, cache clearing won’t target the
    intended path. Consider os.path.expandvars. skills/dev-activity-report-skill/scripts/clear_cache.py:37