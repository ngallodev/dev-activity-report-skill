#!/usr/bin/env python3
"""
Direct pipeline runner — no codex exec overhead.

Phases:
  0  — optional insights snapshot check
  1  — phase1_runner.py  (data gather, fingerprint, cache)
  1.5 — phase1_5_draft.py (cheap model bullet draft; uses claude -p if no SDK)
  2  — claude --model <model> -p (polished report via claude CLI)
  3  — cache verification summary (inline Python)

Usage:
  python3 run_pipeline.py             # background, logs to ~/pipeline-run-<TS>.log
  python3 run_pipeline.py --foreground  # stream all phase output
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Resolve paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ENV_FILE = SKILL_DIR / ".env"


# ── Env loader ────────────────────────────────────────────────────────────────
def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    try:
        from dotenv import dotenv_values  # type: ignore
        env.update({k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None})
        return env
    except ImportError:
        pass
    for line in ENV_FILE.read_text().splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k, v = stripped.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def expand(val: str) -> str:
    return os.path.expandvars(os.path.expanduser(val))


def find_claude_bin() -> str | None:
    """Find the claude CLI binary."""
    import shutil
    return shutil.which("claude")


# ── Notify helper ─────────────────────────────────────────────────────────────
def notify(message: str) -> None:
    for cmd in (["terminal-notifier", "-title", "dev-activity-report", "-message", message],
                ["notify-send", "dev-activity-report", message]):
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    print(f"[notify] {message}", file=sys.stderr)


# ── Claude CLI helper ─────────────────────────────────────────────────────────
def claude_call(
    prompt: str,
    model: str,
    claude_bin: str,
    system_prompt: str | None = None,
    max_tokens: int = 2048,
    timeout: int = 300,
) -> tuple[str, dict[str, int]]:
    """
    Call `claude -p <prompt> --model <model> --output-format json`.
    Returns (text, usage_dict).
    Unsets CLAUDECODE to bypass nested-session guard.
    """
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    cmd = [
        claude_bin,
        "--model", model,
        "--output-format", "json",
        "--max-budget-usd", "1.00",
        "--no-session-persistence",
        "-p", prompt,
    ]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (rc={result.returncode}):\n{result.stderr.strip()}"
        )

    raw = result.stdout.strip()
    # --output-format json returns a JSON object with result and usage
    try:
        obj = json.loads(raw)
        text = obj.get("result", raw)
        cost_usd = obj.get("cost_usd", 0) or 0
        # claude CLI JSON doesn't always return token counts; estimate from cost
        usage = obj.get("usage", {})
        if not usage:
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": cost_usd}
        else:
            usage["cost_usd"] = cost_usd
    except json.JSONDecodeError:
        text = raw
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0}

    return text, usage


# ── Phase 2 prompt ────────────────────────────────────────────────────────────
PHASE2_SYSTEM = """\
You are a senior resume/portfolio writer with excellent creative writing and deep technical understanding.
Stay terse. No meta commentary. No mention of these instructions in output."""

PHASE2_RULES = """\
Write Markdown with exactly these headings:
## Overview
## Key Changes
## Recommendations
## Resume Bullets
## LinkedIn
## Highlights
## Timeline
## Tech Inventory

Rules:
- Resume Bullets: 5–8 bullets, achievement-oriented, past tense, action verbs, quantified where possible.
  For use under "{resume_header}" on a resume.
- LinkedIn: 3–4 sentences, first person, professional but conversational.
- Highlights: flag the 2–3 most resume-worthy items (engineering depth + practical AI integration).
- Timeline: 5 rows, most recent first.
- Tech Inventory: languages, frameworks, AI tools, infra.
- Keep bullets short; no meta commentary.
- Use markers mk + st to separate original vs forked projects.
- Pull AI workflow patterns from ins / cx / cl keys.

Few-shot example input:
Summary JSON: {{"p":[{{"n":"rag-api","cc":3,"fc":["api/router.py"],"hl":["perf","ai-workflow"]}}],"mk":[],"cx":{{"sm":{{"2026-02":4}}}},"ins":[]}}
Draft bullets: - rag-api: 3 commits; themes perf, ai-workflow

Few-shot example output:
## Overview
- Refreshed rag-api with perf + AI workflow tweaks.
## Key Changes
- rag-api: perf-focused tweaks across api/router.py.
## Recommendations
- Ship perf benchmarks.
## Resume Bullets
- Boosted rag-api throughput by tightening router hot paths and validating AI pipeline hooks.
## LinkedIn
- Tuned rag-api for faster routes and smoother AI integration.
## Highlights
- Perf + AI workflow alignment.
## Timeline
- 2026-02: rag-api perf/AI tune-up.
## Tech Inventory
- Languages: Python
"""


def call_phase2(
    data_json: str,
    draft_text: str,
    env: dict[str, str],
    claude_bin: str,
) -> tuple[str, dict[str, int]]:
    resume_header = env.get("RESUME_HEADER", "ngallodev Software, Jan 2025 – Present")
    rules = PHASE2_RULES.format(resume_header=resume_header)
    prompt = (
        f"{rules}\n\n"
        f"Summary JSON (compact):\n{data_json}\n\n"
        f"Draft bullets:\n{draft_text}"
    )
    model = env.get("PHASE2_MODEL", "sonnet")
    timeout = int(env.get("PHASE2_TIMEOUT", 300))
    return claude_call(prompt, model, claude_bin, system_prompt=PHASE2_SYSTEM, timeout=timeout)


# ── Phase 1.5 via claude CLI (when no SDK) ────────────────────────────────────
PHASE15_PROMPT_TMPL = """\
You are a terse assistant drafting a dev activity report.
Input JSON uses abbreviated keys. Write a bullet draft only; no commentary.

Summary:
{summary_json}

Output:
- 5–8 bullets (concise)
- 2 sentence overview
"""


def call_phase15_claude(
    summary: dict,
    env: dict[str, str],
    claude_bin: str,
) -> tuple[str, dict[str, int]]:
    model = env.get("PHASE15_MODEL", "haiku")
    prompt = PHASE15_PROMPT_TMPL.format(
        summary_json=json.dumps(summary, separators=(",", ":"))
    )
    timeout = int(env.get("PHASE15_TIMEOUT", 180))
    return claude_call(prompt, model, claude_bin, timeout=timeout)


# ── Cache verification (Phase 3) ──────────────────────────────────────────────
def phase3_verify(skill_dir: Path) -> None:
    phase1_path = skill_dir / ".phase1-cache.json"
    if not phase1_path.exists():
        print("  phase1 cache missing", flush=True)
        return
    data = json.loads(phase1_path.read_text())
    print(f"  phase1 fingerprint: {data.get('fingerprint', 'n/a')}", flush=True)
    for proj in data.get("data", {}).get("p", []):
        path = Path(proj.get("pt", ""))
        cache = path / ".dev-report-cache.md"
        header = cache.read_text().splitlines()[0] if cache.exists() else "missing"
        print(f"  {proj.get('n', 'project')}: {header}", flush=True)


# ── Token logger wrapper ──────────────────────────────────────────────────────
def log_tokens(phase: str, model: str, usage: dict, env: dict[str, str]) -> None:
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from token_logger import append_usage  # type: ignore
        price_in_key = "PRICE_PHASE15_IN" if phase == "1.5" else "PRICE_PHASE2_IN"
        price_out_key = "PRICE_PHASE15_OUT" if phase == "1.5" else "PRICE_PHASE2_OUT"
        append_usage(
            skill_dir=SKILL_DIR,
            phase=phase,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            price_in=float(env.get(price_in_key, 0) or 0),
            price_out=float(env.get(price_out_key, 0) or 0),
        )
    except Exception as exc:
        print(f"  [token_logger] {exc}", file=sys.stderr)


# ── Benchmark recorder ────────────────────────────────────────────────────────
def record_benchmark(
    run_label: str,
    timings: dict[str, float],
    cache_hit: bool,
    usage15: dict,
    usage2: dict,
    report_path: Path,
    skill_dir: Path,
) -> None:
    """Append a benchmark record to references/benchmarks.jsonl."""
    phase_keys = ("phase1", "phase15", "phase2", "phase3")
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run": run_label,
        "cache_hit": cache_hit,
        "timings_sec": {k: round(v, 3) for k, v in timings.items() if k != "total"},
        "total_sec": round(sum(v for k, v in timings.items() if k in phase_keys), 3),
        "phase15_tokens": usage15,
        "phase2_tokens": usage2,
        "report": str(report_path),
    }
    bmark_file = skill_dir / "references" / "benchmarks.jsonl"
    bmark_file.parent.mkdir(parents=True, exist_ok=True)
    with bmark_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    print(f"  Benchmark logged: {bmark_file}", flush=True)


# ── Main pipeline ─────────────────────────────────────────────────────────────
def run(foreground: bool = True) -> int:
    env = load_env()

    if not ENV_FILE.exists():
        setup = SCRIPT_DIR / "setup_env.py"
        flag = [] if foreground else ["--non-interactive"]
        subprocess.run([sys.executable, str(setup)] + flag, check=False)
        env = load_env()

    apps_dir = expand(env.get("APPS_DIR", "/lump/apps"))
    codex_home = expand(env.get("CODEX_HOME", "~/.codex"))
    claude_home = expand(env.get("CLAUDE_HOME", "~/.claude"))
    for key, val in (("APPS_DIR", apps_dir), ("CODEX_HOME", codex_home), ("CLAUDE_HOME", claude_home)):
        if not val:
            print(f"Missing required .env value: {key}. Run scripts/setup_env.py.", file=sys.stderr)
            return 1

    output_dir = Path(expand(env.get("REPORT_OUTPUT_DIR", "~")))
    prefix = env.get("REPORT_FILENAME_PREFIX", "dev-activity-report")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_out = output_dir / f"{prefix}-{ts}.md"

    if not output_dir.exists():
        print(f"Output directory does not exist: {output_dir}", file=sys.stderr)
        return 1
    if not os.access(output_dir, os.W_OK):
        print(f"Output directory not writable: {output_dir}", file=sys.stderr)
        return 1

    claude_bin = find_claude_bin()
    if not claude_bin:
        print("claude CLI not found on PATH. Install Claude Code to continue.", file=sys.stderr)
        return 1

    timings: dict[str, float] = {}
    wall_start = time.monotonic()

    # ── Phase 0: insights snapshot check ──────────────────────────────────────
    print("== Phase 0: insights snapshot ==", flush=True)
    insights_path = Path(expand(env.get("INSIGHTS_REPORT_PATH", "~/.claude/usage-data/report.html")))
    if insights_path.exists():
        print(f"  Found insights report: {insights_path}", flush=True)
    else:
        print(f"  No insights report at {insights_path} — continuing.", flush=True)

    # ── Phase 1: data gathering ───────────────────────────────────────────────
    phase1_model = env.get("PHASE1_MODEL", "haiku")
    print(f"== Phase 1 ({phase1_model}): data gathering ==", flush=True)
    t0 = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "phase1_runner.py")],
        capture_output=True,   # always capture; print below if foreground
        text=True,
        cwd=str(SKILL_DIR),
    )
    timings["phase1"] = time.monotonic() - t0

    if foreground and result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout)
        print("Phase 1 failed.", file=sys.stderr)
        return 1

    # Find last JSON line in stdout
    phase1_json_str = ""
    for line in reversed((result.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            phase1_json_str = line
            break

    if not phase1_json_str:
        cache_file = SKILL_DIR / ".phase1-cache.json"
        if cache_file.exists():
            raw_cache = json.loads(cache_file.read_text())
            # .phase1-cache.json uses 'fingerprint' key; normalize to pipeline shape
            if "fp" not in raw_cache and "fingerprint" in raw_cache:
                raw_cache["fp"] = raw_cache["fingerprint"]
            if "cache_hit" not in raw_cache:
                raw_cache["cache_hit"] = True  # reading from cache file implies a warm run
            phase1_json_str = json.dumps(raw_cache)
            print("  (read phase1 output from cache file — warm run)", flush=True)
        else:
            print("Phase 1 produced no JSON output and no cache file found.", file=sys.stderr)
            return 1
    else:
        if foreground:
            # Print non-JSON lines (progress output) from phase1
            for line in (result.stdout or "").splitlines():
                if not line.strip().startswith("{"):
                    print(f"  {line}", flush=True)

    phase1_payload = json.loads(phase1_json_str)
    cache_hit = phase1_payload.get("cache_hit", False)
    fp = phase1_payload.get("fp", "n/a")
    print(f"  cache_hit={cache_hit}, fp={fp[:16]}…, elapsed={timings['phase1']:.2f}s", flush=True)

    # ── Phase 1.5: cheap draft ────────────────────────────────────────────────
    phase15_model = env.get("PHASE15_MODEL", phase1_model)
    print(f"== Phase 1.5 ({phase15_model}): draft ==", flush=True)
    t0 = time.monotonic()

    # Try phase1_5_draft.py first (uses openai SDK if available)
    result15 = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "phase1_5_draft.py")],
        input=phase1_json_str,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
    )
    phase15_payload = {}
    usage15: dict = {"prompt_tokens": 0, "completion_tokens": 0}

    if result15.returncode == 0:
        try:
            phase15_payload = json.loads(result15.stdout.strip())
            draft_text = phase15_payload.get("draft", "")
            usage15 = phase15_payload.get("usage", usage15)
            sdk_used = bool(usage15.get("prompt_tokens", 0))
        except json.JSONDecodeError:
            draft_text = ""
            sdk_used = False
    else:
        draft_text = ""
        sdk_used = False

    # If SDK produced no tokens (heuristic fallback), use claude CLI instead
    if not sdk_used:
        print(f"  SDK unavailable; calling claude CLI for Phase 1.5 ({phase15_model})", flush=True)
        try:
            summary = phase1_payload.get("data", phase1_payload)
            draft_text, usage15 = call_phase15_claude(summary, env, claude_bin)
        except Exception as exc:
            print(f"  claude CLI Phase 1.5 failed: {exc}", file=sys.stderr)
            # Fall back to the heuristic draft from phase1_5_draft.py
            if phase15_payload:
                draft_text = phase15_payload.get("draft", "")
            if not draft_text:
                print("Phase 1.5 produced no draft.", file=sys.stderr)
                return 1
            print("  Using heuristic fallback draft.", flush=True)

    timings["phase15"] = time.monotonic() - t0
    print(
        f"  draft lines={len(draft_text.splitlines())}, "
        f"tokens={usage15}, elapsed={timings['phase15']:.2f}s",
        flush=True,
    )
    log_tokens("1.5", phase15_model, usage15, env)

    # ── Phase 2: polished report ──────────────────────────────────────────────
    phase2_model = env.get("PHASE2_MODEL", "sonnet")
    print(f"== Phase 2 ({phase2_model}): report ==", flush=True)
    t0 = time.monotonic()
    data_json = json.dumps(phase1_payload.get("data", phase1_payload), separators=(",", ":"))
    try:
        report_text, usage2 = call_phase2(data_json, draft_text, env, claude_bin)
    except Exception as exc:
        print(f"Phase 2 failed: {exc}", file=sys.stderr)
        return 1
    timings["phase2"] = time.monotonic() - t0
    print(f"  tokens={usage2}, elapsed={timings['phase2']:.2f}s", flush=True)
    log_tokens("2", phase2_model, usage2, env)

    # Write report
    report_out.write_text(report_text, encoding="utf-8")
    print(f"  Report written: {report_out}", flush=True)

    # ── Phase 3: cache verification ───────────────────────────────────────────
    phase3_model = env.get("PHASE3_MODEL", "haiku")
    print(f"== Phase 3 ({phase3_model}): cache verification ==", flush=True)
    t0 = time.monotonic()
    phase3_verify(SKILL_DIR)
    timings["phase3"] = time.monotonic() - t0

    total = time.monotonic() - wall_start
    timings["total"] = total
    run_label = "cold" if not cache_hit else "warm"
    print(
        f"== Done ({run_label}) — total {total:.2f}s "
        f"(p1={timings['phase1']:.2f}s p1.5={timings['phase15']:.2f}s "
        f"p2={timings['phase2']:.2f}s) ==",
        flush=True,
    )

    record_benchmark(run_label, timings, cache_hit, usage15, usage2, report_out, SKILL_DIR)
    notify(f"Report completed: {report_out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct pipeline runner for dev-activity-report.")
    parser.add_argument("--foreground", action="store_true",
                        help="Stream output (default: background via nohup)")
    args = parser.parse_args()

    if not args.foreground:
        env = load_env()
        log_dir = Path(expand(env.get("REPORT_OUTPUT_DIR", "~")))
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_file = log_dir / f"pipeline-run-{ts}.log"
        with open(log_file, "w") as lf:
            proc = subprocess.Popen(
                [sys.executable, __file__, "--foreground"],
                stdout=lf,
                stderr=lf,
                start_new_session=True,
            )
        print(f"Pipeline started in background (PID {proc.pid}). Log: {log_file}", flush=True)
        return

    sys.exit(run(foreground=True))


if __name__ == "__main__":
    main()
