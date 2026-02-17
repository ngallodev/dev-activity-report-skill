#!/usr/bin/env python3
"""Cache validation: cold run → warm run → assert correctness.

Runs phase1_runner.py twice:
  1. Cold run (after clearing cache): expects cache_hit=false
  2. Warm run (cache written by cold run): expects cache_hit=true, same fp, no mtime drift

Exit codes:
  0 — all assertions passed
  1 — assertion failure (details on stderr)
  2 — script/environment error

Usage:
    python3 skills/dev-activity-report-skill/scripts/testing/validate_cache.py
    python3 skills/dev-activity-report-skill/scripts/testing/validate_cache.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent.parent
RUNNER = SKILL_DIR / "scripts" / "phase1_runner.py"
CACHE_FILE = SKILL_DIR / ".phase1-cache.json"
CLEAR_CACHE = SKILL_DIR / "scripts" / "clear_cache.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str, verbose: bool) -> None:
    if verbose:
        print(f"  {msg}", flush=True)


def run_phase1(label: str, verbose: bool) -> dict:
    """Run phase1_runner.py and return the parsed JSON output."""
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
    )
    elapsed = time.perf_counter() - start

    if result.returncode != 0:
        print(f"FAIL [{label}] phase1_runner.py exited {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(2)

    raw = result.stdout.strip()
    if not raw:
        print(f"FAIL [{label}] phase1_runner.py produced no output", file=sys.stderr)
        sys.exit(2)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FAIL [{label}] could not parse JSON output: {exc}", file=sys.stderr)
        print(f"  raw (first 500): {raw[:500]}", file=sys.stderr)
        sys.exit(2)

    log(f"[{label}] elapsed={elapsed:.2f}s  fp={payload.get('fp', '')[:12]}...  cache_hit={payload.get('cache_hit')}", verbose)
    if result.stderr.strip():
        log(f"[{label}] stderr: {result.stderr.strip()[:200]}", verbose)

    return payload


def assert_eq(label: str, field: str, expected, actual) -> None:
    if actual != expected:
        print(f"FAIL [{label}] {field}: expected {expected!r}, got {actual!r}", file=sys.stderr)
        sys.exit(1)


def assert_cache_file_exists() -> None:
    if not CACHE_FILE.exists():
        print(f"FAIL cache file not written after cold run: {CACHE_FILE}", file=sys.stderr)
        sys.exit(1)


def cache_mtime() -> float:
    try:
        return CACHE_FILE.stat().st_mtime
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Main validation logic
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate cold→warm cache behaviour of phase1_runner.py")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-step diagnostics")
    args = parser.parse_args()
    verbose = args.verbose

    print("validate_cache: starting", flush=True)
    print(f"  skill_dir : {SKILL_DIR}", flush=True)
    print(f"  runner    : {RUNNER}", flush=True)
    print(f"  cache_file: {CACHE_FILE}", flush=True)

    if not RUNNER.exists():
        print(f"FAIL phase1_runner.py not found at {RUNNER}", file=sys.stderr)
        sys.exit(2)

    # ------------------------------------------------------------------
    # Step 1 — clear cache so cold run is guaranteed
    # ------------------------------------------------------------------
    print("\n[1/4] Clearing cache...", flush=True)
    clear_result = subprocess.run(
        [sys.executable, str(CLEAR_CACHE), "--confirm"],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
    )
    if clear_result.returncode != 0:
        print(f"FAIL clear_cache.py exited {clear_result.returncode}", file=sys.stderr)
        print(clear_result.stderr, file=sys.stderr)
        sys.exit(2)
    log(f"clear_cache output: {clear_result.stdout.strip()}", verbose)

    if CACHE_FILE.exists():
        print(f"FAIL cache file still exists after clear: {CACHE_FILE}", file=sys.stderr)
        sys.exit(1)
    print("  OK cache cleared", flush=True)

    # ------------------------------------------------------------------
    # Step 2 — cold run: cache_hit must be false, cache file must be written
    # ------------------------------------------------------------------
    print("\n[2/4] Cold run (no cache)...", flush=True)
    cold = run_phase1("cold", verbose)

    assert_eq("cold", "cache_hit", False, cold.get("cache_hit"))
    if not cold.get("fp"):
        print("FAIL [cold] fp is empty", file=sys.stderr)
        sys.exit(1)

    assert_cache_file_exists()
    mtime_after_cold = cache_mtime()
    cold_fp = cold["fp"]
    print(f"  OK cold: cache_hit=False, fp={cold_fp[:16]}..., cache written", flush=True)

    # ------------------------------------------------------------------
    # Step 3 — warm run: cache_hit must be true, fp must match, no file rewrite
    # ------------------------------------------------------------------
    print("\n[3/4] Warm run (cache present)...", flush=True)
    warm = run_phase1("warm", verbose)

    assert_eq("warm", "cache_hit", True, warm.get("cache_hit"))
    assert_eq("warm", "fp", cold_fp, warm.get("fp"))

    # Fingerprint must be stable — the cache file's mtime should NOT change on a warm hit
    mtime_after_warm = cache_mtime()
    if mtime_after_warm != mtime_after_cold:
        print(
            f"FAIL [warm] cache file was rewritten during warm run "
            f"(mtime changed: {mtime_after_cold} → {mtime_after_warm}). "
            "Possible self-invalidating cache loop.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  OK warm: cache_hit=True, fp stable, mtime unchanged ({mtime_after_warm})", flush=True)

    # ------------------------------------------------------------------
    # Step 4 — verify cache file content matches reported fingerprint
    # ------------------------------------------------------------------
    print("\n[4/4] Verifying cache file integrity...", flush=True)
    try:
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL cache file unreadable or not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    cached_fp = cached.get("fingerprint", "")
    if cached_fp != cold_fp:
        print(
            f"FAIL cache file fingerprint {cached_fp!r} does not match "
            f"run fp {cold_fp!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    cached_at = cached.get("cached_at", "(missing)")
    print(f"  OK cache file: fingerprint matches, cached_at={cached_at}", flush=True)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\nvalidate_cache: ALL ASSERTIONS PASSED", flush=True)
    print(f"  cold run fp  : {cold_fp}", flush=True)
    print(f"  warm run fp  : {warm['fp']}", flush=True)
    print(f"  cache mtime  : {mtime_after_cold} (unchanged after warm run)", flush=True)


if __name__ == "__main__":
    main()
