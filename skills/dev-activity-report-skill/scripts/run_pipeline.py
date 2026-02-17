#!/usr/bin/env python3
"""
Direct pipeline runner — no codex exec overhead.

Phases:
  0  — optional insights snapshot check
  1  — phase1_runner.py  (data gather, fingerprint, cache)
  1.5 — phase1_5_draft.py (cheap model bullet draft; uses claude -p if no SDK)
  2  — claude --model <model> -p (JSON-only analysis via claude CLI)
  2.5 — render_report.py (md/html render from JSON)
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


def slugify(value: str) -> str:
    out = []
    for ch in value.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "_", "-", "."):
            if out and out[-1] != "-":
                out.append("-")
    return "".join(out).strip("-")


def expand_compact_payload(compact: dict) -> dict:
    projects = []
    for proj in compact.get("p", []) or []:
        projects.append(
            {
                "name": proj.get("n", ""),
                "path": proj.get("pt", ""),
                "status": proj.get("st", "orig"),
                "commit_count": int(proj.get("cc", 0) or 0),
                "file_changes": proj.get("sd", ""),
                "changed_files": proj.get("fc", []) or [],
                "commit_messages": proj.get("msg", []) or [],
                "themes": proj.get("hl", []) or [],
                "fingerprint": proj.get("fp", ""),
            }
        )

    ownership_markers = []
    for marker in compact.get("mk", []) or []:
        ownership_markers.append(
            {
                "marker": marker.get("m", ""),
                "path": marker.get("p", ""),
            }
        )

    extra_scan_dirs = []
    for item in compact.get("x", []) or []:
        extra_scan_dirs.append(
            {
                "path": item.get("p", ""),
                "exists": bool(item.get("exists", False)),
                "is_git": bool(item.get("git", False)),
                "key_files": item.get("kf", []) or [],
                "fingerprint": item.get("fp", ""),
            }
        )

    claude = compact.get("cl", {}) or {}
    codex = compact.get("cx", {}) or {}
    stats = compact.get("stats", {}) or {}

    return {
        "apps_dir": compact.get("ad", ""),
        "projects": projects,
        "ownership_markers": ownership_markers,
        "extra_scan_dirs": extra_scan_dirs,
        "claude_home": {
            "skills": claude.get("sk", []) or [],
            "hooks": claude.get("hk", []) or [],
            "agents": claude.get("ag", []) or [],
        },
        "codex_home": {
            "session_months": codex.get("sm", {}) or {},
            "active_workdirs": codex.get("cw", []) or [],
            "skills": codex.get("sk", []) or [],
        },
        "insights": compact.get("ins", []) or [],
        "stats": {
            "total": stats.get("total"),
            "stale": stats.get("stale"),
            "cached": stats.get("cached"),
        },
    }


def build_source_summary(expanded: dict) -> dict:
    projects = []
    for proj in expanded.get("projects", []) or []:
        name = proj.get("name") or Path(proj.get("path", "")).name
        proj_id = slugify(name) if name else ""
        projects.append(
            {
                "id": proj_id,
                "name": name,
                "path": proj.get("path", ""),
                "status": proj.get("status", "orig"),
                "commit_count": proj.get("commit_count", 0),
                "file_changes": proj.get("file_changes", ""),
                "themes": proj.get("themes", []) or [],
            }
        )

    return {
        "projects": projects,
        "extra_scan_dirs": expanded.get("extra_scan_dirs", []) or [],
        "claude_home": expanded.get("claude_home", {}) or {},
        "codex_home": expanded.get("codex_home", {}) or {},
        "insights": expanded.get("insights", []) or [],
    }


KEY_LABEL_MAP = {
    "mk": "Ownership markers",
    "st": "Project status",
    "x": "Extra scan dirs",
    "cl": "Claude home",
    "cx": "Codex home",
    "ins": "Insights",
    "stats": "Stats",
}


def normalize_label(text: str) -> str:
    if not text:
        return text
    stripped = text.strip()
    for key, label in KEY_LABEL_MAP.items():
        variants = {key, key.upper(), key.capitalize()}
        for variant in variants:
            if stripped == variant:
                return label
            if stripped.startswith(f"**{variant}**"):
                return label + stripped[len(f"**{variant}**"):]
            for sep in (":", " ", " —", " -"):
                if stripped.startswith(variant + sep):
                    return label + stripped[len(variant):]
    return text


def normalize_sections(sections: dict) -> dict:
    key_changes = sections.get("key_changes")
    if isinstance(key_changes, list):
        for item in key_changes:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            if isinstance(title, str):
                item["title"] = normalize_label(title)
            bullets = item.get("bullets")
            if isinstance(bullets, list):
                item["bullets"] = [normalize_label(b) if isinstance(b, str) else b for b in bullets]
    return sections


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
Return JSON only (no Markdown, no code fences). Output must be a single valid JSON object
with the following shape:

{
  "sections": {
    "overview":{"bullets":["..."]},
    "key_changes":[{"title":"<label>","project_id":"<id or null>","bullets":["..."],"tags":["..."]}],
    "recommendations":[{"text":"...","priority":"low|medium|high","evidence_project_ids":["..."]}],
    "resume_bullets":[{"text":"...","evidence_project_ids":["..."]}],
    "linkedin":{"sentences":["..."]},
    "highlights":[{"title":"...","rationale":"...","evidence_project_ids":["..."]}],
    "timeline":[{"date":"YYYY-MM-DD","event":"...","project_ids":["..."]}],
    "tech_inventory":{"languages":["..."],"frameworks":["..."],"ai_tools":["..."],"infra":["..."]}
  },
  "render_hints":{"preferred_outputs":["md","html"],"style":"concise","tone":"professional"}
}

Rules:
- Output JSON only; no Markdown.
- Input JSON uses compact keys (see PAYLOAD_REFERENCE for p/mk/x/cl/cx/ins/stats).
- Resume bullets: 5–8 items, achievement-oriented, past tense, quantified where possible,
  for use under "{resume_header}".
- LinkedIn: 3–4 sentences, first person, professional but conversational.
- Highlights: 2–3 items, engineering depth + practical AI integration.
- Timeline: 5 rows, most recent first.
- Tech Inventory: languages, frameworks, AI tools, infra.
- Keep bullets short; no meta commentary.
"""


def call_phase2(
    compact_json: str,
    draft_text: str,
    env: dict[str, str],
    claude_bin: str,
) -> tuple[str, dict[str, int]]:
    resume_header = env.get("RESUME_HEADER", "ngallodev Software, Jan 2025 – Present")
    rules = PHASE2_RULES.format(resume_header=resume_header)
    prompt = (
        f"{rules}\n\n"
        f"Summary JSON (compact):\n{compact_json}\n\n"
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
        if cache.exists():
            lines = cache.read_text().splitlines()
            header = lines[0] if lines else "empty"
        else:
            header = "missing"
        print(f"  {proj.get('n', 'project')}: {header}", flush=True)


# ── Token logger wrapper ──────────────────────────────────────────────────────
def normalize_usage(usage: dict) -> tuple[int, int]:
    """Map Claude CLI usage fields to (prompt_tokens, completion_tokens)."""
    if "prompt_tokens" in usage or "completion_tokens" in usage:
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        return prompt_tokens, completion_tokens

    cache_create = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    prompt_tokens = cache_create + cache_read if (cache_create or cache_read) else input_tokens
    completion_tokens = int(usage.get("output_tokens", 0) or 0)
    return prompt_tokens, completion_tokens


def log_tokens(phase: str, model: str, usage: dict, env: dict[str, str]) -> None:
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from token_logger import append_usage  # type: ignore
        price_in_key = "PRICE_PHASE15_IN" if phase == "1.5" else "PRICE_PHASE2_IN"
        price_out_key = "PRICE_PHASE15_OUT" if phase == "1.5" else "PRICE_PHASE2_OUT"
        prompt_tokens, completion_tokens = normalize_usage(usage)
        append_usage(
            skill_dir=SKILL_DIR,
            phase=phase,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
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
    env: dict[str, str],
) -> None:
    """Append a benchmark record to BENCHMARK_LOG_PATH (default: REPORT_OUTPUT_DIR/benchmarks.jsonl)."""
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
    bmark_override = env.get("BENCHMARK_LOG_PATH")
    if bmark_override:
        bmark_file = Path(expand(bmark_override))
    else:
        output_dir = Path(expand(env.get("REPORT_OUTPUT_DIR", "~")))
        bmark_file = output_dir / "benchmarks.jsonl"
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
    base_name = f"{prefix}-{ts}"
    report_json = output_dir / f"{base_name}.json"
    output_formats = [f.strip().lower() for f in env.get("REPORT_OUTPUT_FORMATS", "md").split(",") if f.strip()]
    if not output_formats:
        output_formats = ["md"]
    include_source_payload = env.get("INCLUDE_SOURCE_PAYLOAD", "false").lower() == "true"

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
    compact_payload = phase1_payload.get("data", phase1_payload)

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
    compact_json = json.dumps(compact_payload, separators=(",", ":"))
    try:
        report_text, usage2 = call_phase2(compact_json, draft_text, env, claude_bin)
    except Exception as exc:
        print(f"Phase 2 failed: {exc}", file=sys.stderr)
        return 1
    timings["phase2"] = time.monotonic() - t0
    print(f"  tokens={usage2}, elapsed={timings['phase2']:.2f}s", flush=True)
    log_tokens("2", phase2_model, usage2, env)

    # Parse Phase 2 JSON and write structured output
    try:
        phase2_obj = json.loads(report_text)
    except json.JSONDecodeError as exc:
        print(f"Phase 2 output was not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(phase2_obj, dict):
        print("Phase 2 output JSON must be an object.", file=sys.stderr)
        return 1

    if "sections" in phase2_obj:
        sections = phase2_obj.get("sections") or {}
        render_hints = phase2_obj.get("render_hints") or {}
    else:
        if any(k in phase2_obj for k in ("overview", "key_changes", "recommendations", "resume_bullets",
                                         "linkedin", "highlights", "timeline", "tech_inventory")):
            sections = phase2_obj
            render_hints = {}
        else:
            print("Phase 2 output missing 'sections' block.", file=sys.stderr)
            return 1

    expanded_payload = expand_compact_payload(compact_payload)
    source_summary = build_source_summary(expanded_payload)
    sections = normalize_sections(sections)

    report_obj = {
        "schema_version": "dev-activity-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run": {
            "phase1_fingerprint": fp,
            "cache_hit": bool(cache_hit),
            "models": {"phase1": phase1_model, "phase15": phase15_model, "phase2": phase2_model},
        },
        "source_summary": source_summary,
        "sections": sections,
        "render_hints": render_hints,
        "source_payload": compact_payload if include_source_payload else None,
    }
    report_json.write_text(json.dumps(report_obj, separators=(",", ":")), encoding="utf-8")
    print(f"  Report JSON written: {report_json}", flush=True)

    # ── Phase 2.5: render outputs ─────────────────────────────────────────────
    print(f"== Phase 2.5: render outputs ({', '.join(output_formats)}) ==", flush=True)
    render_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "render_report.py"),
        "--input", str(report_json),
        "--output-dir", str(output_dir),
        "--base-name", base_name,
        "--formats", ",".join(output_formats),
    ]
    result_render = subprocess.run(render_cmd, capture_output=True, text=True)
    if result_render.returncode != 0:
        if result_render.stderr:
            print(result_render.stderr.strip(), file=sys.stderr)
        print("Phase 2.5 render failed.", file=sys.stderr)
        return 1
    for fmt in output_formats:
        out_path = output_dir / f"{base_name}.{fmt}"
        if out_path.exists():
            print(f"  Rendered: {out_path}", flush=True)

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

    report_path_for_benchmark = report_json
    if "md" in output_formats:
        report_path_for_benchmark = output_dir / f"{base_name}.md"
    record_benchmark(run_label, timings, cache_hit, usage15, usage2, report_path_for_benchmark, SKILL_DIR, env)

    notify_path = report_path_for_benchmark
    if output_formats:
        notify_path = output_dir / f"{base_name}.{output_formats[0]}"
    notify(f"Report completed: {notify_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct pipeline runner for dev-activity-report.")
    parser.add_argument("--foreground", action="store_true",
                        help="Stream output (default: background via nohup)")
    args = parser.parse_args()

    if not args.foreground:
        env = load_env()
        log_dir = Path(expand(env.get("REPORT_OUTPUT_DIR", "~")))
        if not log_dir.exists():
            print(f"Output directory does not exist: {log_dir}", file=sys.stderr)
            sys.exit(1)
        if not os.access(log_dir, os.W_OK):
            print(f"Output directory not writable: {log_dir}", file=sys.stderr)
            sys.exit(1)
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
