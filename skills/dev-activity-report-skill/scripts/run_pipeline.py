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
  python3 run_pipeline.py --interactive --foreground  # review Phase 2 JSON before render
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import urllib.parse
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


def parse_paths(raw: str) -> list[str]:
    if not raw:
        return []
    return [p for p in raw.replace(",", " ").split() if p.strip()]


def resolve_scan_roots(env: dict[str, str], cli_roots: list[str] | None = None) -> list[str]:
    if cli_roots:
        raw_roots = [r for r in cli_roots if r.strip()]
    else:
        raw_roots = parse_paths(env.get("APPS_DIRS", "")) or [env.get("APPS_DIR", "~/projects")]
    roots: list[str] = []
    seen: set[str] = set()
    for raw in raw_roots:
        expanded = expand(raw)
        if expanded in seen:
            continue
        seen.add(expanded)
        roots.append(expanded)
    return roots


def resolve_since(env: dict[str, str], cli_since: str | None = None) -> str | None:
    if cli_since and cli_since.strip():
        return cli_since.strip()
    for key in ("REPORT_SINCE", "GIT_SINCE", "SINCE"):
        value = env.get(key, "")
        if value and value.strip():
            return value.strip()
    return None


def env_bool(env: dict[str, str], key: str, default: bool = False) -> bool:
    raw = env.get(key, "")
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
                "root": proj.get("rt", ""),
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
        "apps_dirs": compact.get("ads", []) or [],
        "since": compact.get("sn", ""),
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
        "insights_meta": compact.get("insm", {}) or {},
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
                "root": proj.get("root", ""),
                "status": proj.get("status", "orig"),
                "commit_count": proj.get("commit_count", 0),
                "file_changes": proj.get("file_changes", ""),
                "themes": proj.get("themes", []) or [],
            }
        )

    return {
        "apps_dir": expanded.get("apps_dir", ""),
        "apps_dirs": expanded.get("apps_dirs", []) or [],
        "since": expanded.get("since", ""),
        "projects": projects,
        "extra_scan_dirs": expanded.get("extra_scan_dirs", []) or [],
        "claude_home": expanded.get("claude_home", {}) or {},
        "codex_home": expanded.get("codex_home", {}) or {},
        "insights": expanded.get("insights", []) or [],
        "insights_meta": expanded.get("insights_meta", {}) or {},
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


def path_to_file_url(path: str) -> str:
    if not path:
        return ""
    return Path(path).resolve().as_uri()


def _extract_insights_text_lines(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    # Lightweight HTML-to-text extraction without extra dependencies.
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|li|h1|h2|h3|h4|h5|h6|div|section|article)>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw)

    lines: list[str] = []
    for line in text.splitlines():
        cleaned = " ".join(line.split()).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def extract_insights_quote_entries(
    env: dict[str, str],
    claude_bin: str | None = None,
) -> tuple[list[dict[str, str]], str]:
    """Return (quote_entries, source_path) for optional Phase 2 prompt context."""
    if not env_bool(env, "INCLUDE_CLAUDE_INSIGHTS_QUOTES", default=False):
        return [], ""

    path = Path(expand(env.get("INSIGHTS_REPORT_PATH", "~/.claude/usage-data/report.html")))
    if not path.exists():
        return [], str(path)

    lines = _extract_insights_text_lines(path)
    if not lines:
        return [], str(path)

    max_quotes = int(env.get("CLAUDE_INSIGHTS_QUOTES_MAX", 8) or 8)
    max_chars = int(env.get("CLAUDE_INSIGHTS_QUOTES_MAX_CHARS", 2000) or 2000)
    source_path = str(path)
    source_link = path_to_file_url(source_path)

    # Prefer LLM-based extraction to avoid headings/labels; fall back to heuristic if needed.
    quotes: list[str] = []
    if claude_bin:
        model = env.get("INSIGHTS_QUOTES_MODEL", env.get("PHASE15_MODEL", "haiku"))
        # Cap the input size to keep prompt size bounded.
        max_lines = 200
        trimmed = lines[:max_lines]
        numbered = "\n".join(f"{i+1}. {line}" for i, line in enumerate(trimmed))
        prompt = (
            "Select up to {max_q} substantive insight sentences from the list below.\n"
            "Rules:\n"
            "- Return JSON only: {{\"quotes\":[\"...\"]}}\n"
            "- Quotes must be exact full lines from the list (verbatim, no edits).\n"
            "- Exclude headings, labels, UI chrome, short fragments, and section titles.\n"
            "- Prefer lines with concrete metrics, outcomes, or workflow insights.\n"
            "- Do not include more than {max_chars} total characters across all quotes.\n\n"
            "Lines:\n{lines}\n"
        ).format(max_q=max_quotes, max_chars=max_chars, lines=numbered)
        try:
            raw, _usage = claude_call(prompt, model, claude_bin, system_prompt="Return JSON only.")
            obj = parse_llm_json_output(raw)
            raw_quotes = obj.get("quotes") if isinstance(obj, dict) else None
            if isinstance(raw_quotes, list):
                for q in raw_quotes:
                    if isinstance(q, str) and q.strip():
                        quotes.append(q.strip())
        except Exception:
            quotes = []

    if not quotes:
        keywords = (
            "usage", "pattern", "wins", "friction", "outcomes", "tool",
            "session", "workflow", "insight", "delegate", "automation", "report",
            "tokens", "hours", "commits", "files", "sessions", "productivity",
        )
        candidates: list[str] = []
        for line in lines:
            # Skip lines that look like CSS/code artifacts
            if "{" in line or "}" in line or line.startswith("--") or line.startswith("."):
                continue
            cleaned = line.strip()
            if not cleaned:
                continue
            lower = cleaned.lower()
            is_candidate = (
                cleaned.startswith("-")
                or cleaned.startswith("•")
                or any(k in lower for k in keywords)
                or len(cleaned.split()) >= 9
            )
            if is_candidate and cleaned not in candidates:
                candidates.append(cleaned)
        quotes = candidates
    selected: list[dict[str, str]] = []
    total = 0
    for line in quotes:
        if total + len(line) > max_chars and selected:
            break
        selected.append(
            {
                "quote": line,
                "source_path": source_path,
                "source_link": source_link,
            }
        )
        total += len(line)
        if len(selected) >= max_quotes:
            break
    return selected, source_path


def parse_insights_sections(insights_lines: list[str], env: dict[str, str]) -> dict:
    """Parse phase-1 insights markdown tail into structured sections with links."""
    log_path = SKILL_DIR / "references" / "examples" / "insights" / "insights-log.md"
    report_path = Path(expand(env.get("INSIGHTS_REPORT_PATH", "~/.claude/usage-data/report.html")))
    log_url = path_to_file_url(str(log_path))
    report_url = path_to_file_url(str(report_path))

    sections: list[dict[str, object]] = []
    current_date = ""
    current_title = ""
    content: list[str] = []

    def flush_current() -> None:
        nonlocal current_title, content
        if not current_title:
            return
        section_id = slugify(current_title) or "insights"
        sections.append(
            {
                "id": section_id,
                "title": current_title,
                "entry_date": current_date,
                "content": content[:],
                "link": f"{log_url}#{urllib.parse.quote(section_id)}" if log_url else "",
                "report_link": f"{report_url}#{urllib.parse.quote(section_id)}" if report_url else "",
            }
        )
        current_title = ""
        content = []

    for raw in insights_lines:
        line = (raw or "").strip()
        if not line:
            continue
        if line.startswith("## "):
            flush_current()
            current_date = line[3:].strip()
            continue
        if line.startswith("### "):
            flush_current()
            current_title = line[4:].strip()
            continue
        if line.startswith("#"):
            continue
        if not current_title:
            current_title = "Insights Notes"
        content.append(line)

    flush_current()

    return {
        "source": {
            "log_path": str(log_path),
            "log_link": log_url,
            "report_path": str(report_path),
            "report_link": report_url,
        },
        "sections": sections,
    }


def parse_llm_json_output(raw_text: str) -> dict:
    """Parse JSON object from LLM output, tolerating markdown code fences."""
    decoder = json.JSONDecoder()
    text = (raw_text or "").strip()
    candidates = [text]

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidates.insert(0, "\n".join(lines).strip())

    last_err: json.JSONDecodeError | None = None
    for candidate in candidates:
        chunk = candidate.strip()
        for pos in (0, chunk.find("{"), chunk.find("[")):
            if pos < 0:
                continue
            snippet = chunk[pos:].lstrip()
            try:
                obj, end = decoder.raw_decode(snippet)
            except json.JSONDecodeError as exc:
                last_err = exc
                continue
            if snippet[end:].strip():
                continue
            if not isinstance(obj, dict):
                raise json.JSONDecodeError("Top-level JSON must be an object", snippet, 0)
            return obj

    if last_err:
        raise last_err
    raise json.JSONDecodeError("No JSON object found in model output", text, 0)


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

{{
  "sections": {{
    "overview":{{"bullets":["..."]}},
    "key_changes":[{{"title":"<label>","project_id":"<id or null>","bullets":["..."],"tags":["..."]}}],
    "recommendations":[{{"text":"...","priority":"low|medium|high","evidence_project_ids":["..."]}}],
    "resume_bullets":[{{"text":"...","evidence_project_ids":["..."]}}],
    "linkedin":{{"sentences":["..."]}},
    "highlights":[{{"title":"...","rationale":"...","evidence_project_ids":["..."]}}],
    "timeline":[{{"date":"YYYY-MM-DD","event":"...","project_ids":["..."]}}],
    "tech_inventory":{{"languages":["..."],"frameworks":["..."],"ai_tools":["..."],"infra":["..."]}},
    "insights_quotes":[{{"quote":"...","source_path":"...","source_link":"...","section_id":"...","section_title":"..."}}]
  }},
  "render_hints":{{"preferred_outputs":["md","html"],"style":"concise","tone":"professional"}}
}}

Rules:
- Output JSON only; no Markdown.
- Input JSON uses compact keys (see PAYLOAD_REFERENCE for p/mk/x/cl/cx/ins/stats).
- Resume bullets: 5–8 items, achievement-oriented, past tense, quantified where possible,
  for use under "{resume_header}".
- LinkedIn: 3–4 sentences, first person, professional but conversational.
- Highlights: 2–3 items, engineering depth + practical AI integration.
- Timeline: 5 rows, most recent first.
- Tech Inventory: languages, frameworks, AI tools, infra.
- insights_quotes is optional; include 0-6 entries when relevant and preserve source fields.
- Keep bullets short; no meta commentary.
"""


def extract_insights_quotes(
    env: dict[str, str],
    claude_bin: str | None = None,
) -> tuple[str, str]:
    """Return (insights_block, source_path) for optional Phase 2 prompt context."""
    entries, source = extract_insights_quote_entries(env, claude_bin=claude_bin)
    if not entries:
        return "", source
    block = "\n".join(f'- "{item.get("quote", "")}"' for item in entries if item.get("quote"))
    return block, source


def call_phase2(
    compact_json: str,
    draft_text: str,
    env: dict[str, str],
    claude_bin: str,
) -> tuple[str, dict[str, int]]:
    resume_header = env.get("RESUME_HEADER", "Your Name, Jan 2025 – Present")
    rules = PHASE2_RULES.format(resume_header=resume_header)
    extra_rules = (env.get("PHASE2_RULES_EXTRA") or env.get("PHASE2_PROMPT_PREFIX") or "").strip()
    extra_rules_block = ""
    if extra_rules:
        extra_rules_block = (
            "Additional user rules from .env (apply without changing the JSON schema):\n"
            f"{extra_rules}\n\n"
        )
    insights_block, insights_source = extract_insights_quotes(env, claude_bin=claude_bin)
    insight_quote_entries, _ = extract_insights_quote_entries(env, claude_bin=claude_bin)
    insights_prompt_block = ""
    if insights_block:
        quotes_json = json.dumps(insight_quote_entries, separators=(",", ":"))
        insights_prompt_block = (
            f"Claude insights report excerpts (source: {insights_source}):\n"
            f"{insights_block}\n\n"
            f"Insights quote reference JSON (use this for sections.insights_quotes):\n{quotes_json}\n\n"
            "If you use these excerpts, include short attribution text in the relevant bullet/sentence "
            '(e.g., "(source: Claude insights report)").\n\n'
        )
    prompt = (
        f"{rules}\n\n"
        f"{extra_rules_block}"
        f"{insights_prompt_block}"
        f"Summary JSON (compact):\n{compact_json}\n\n"
        f"Draft bullets:\n{draft_text}"
    )
    model = env.get("PHASE2_MODEL", "sonnet")
    timeout = int(env.get("PHASE2_TIMEOUT", 300))
    return claude_call(prompt, model, claude_bin, system_prompt=PHASE2_SYSTEM, timeout=timeout)


# ── Phase 1.5 via claude CLI (when no SDK) ────────────────────────────────────
PHASE15_TERSE_TMPL = """\
You are a terse assistant drafting a dev activity report.
Input JSON uses abbreviated keys. Write a bullet draft only; no commentary.

Output:
- 5–8 bullets (concise)
- 2 sentence overview
"""

PHASE15_THOROUGH_TMPL = """\
You are a sharp-eyed engineering analyst drafting a dev activity report.
Input JSON uses abbreviated keys. Be opinionated, specific, and colorful — \
call out what's impressive, what looks risky or neglected, and what deserves \
more attention. Speak plainly; no hedging.

Output (same structure as terse mode, richer content):
- 8–12 bullets covering highlights AND lowlights
  • Highlights: quantify wins, name specific projects/commits/themes
  • Lowlights: flag stale projects, missing tests, low commit counts,
    or anything that would raise a hiring-manager's eyebrow
- 3–4 sentence overview with an honest assessment of the period's output
- 2–3 'watch-out' notes: things that need attention before the next report
"""


def call_phase15_claude(
    summary: dict,
    env: dict[str, str],
    claude_bin: str,
) -> tuple[str, dict[str, int]]:
    model = env.get("PHASE15_MODEL", "haiku")
    thorough = env.get("PHASE15_THOROUGH", "false").strip().lower() in {"1", "true", "yes", "on"}
    prompt = PHASE15_THOROUGH_TMPL if thorough else PHASE15_TERSE_TMPL
    extra_rules = (env.get("PHASE15_RULES_EXTRA") or env.get("PHASE15_PROMPT_PREFIX") or "").strip()
    if extra_rules:
        prompt = (
            f"{prompt}\n\n"
            "Additional user rules from .env (must not alter required output format):\n"
            f"{extra_rules}"
        )
    prompt = (
        f"{prompt}\n\n"
        "Summary JSON (read-only context; do not rewrite it):\n"
        f"{json.dumps(summary, separators=(',', ':'))}"
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
def should_run_interactive(interactive: bool) -> bool:
    if not interactive:
        return False
    if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}:
        print("  Interactive mode skipped in CI.", flush=True)
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("  Interactive mode skipped (no TTY).", flush=True)
        return False
    return True


def run(
    foreground: bool = True,
    interactive: bool = False,
    since: str | None = None,
    refresh: bool = False,
    roots: list[str] | None = None,
) -> int:
    env = load_env()

    if not ENV_FILE.exists():
        setup = SCRIPT_DIR / "setup_env.py"
        flag = [] if foreground else ["--non-interactive"]
        subprocess.run([sys.executable, str(setup)] + flag, check=False)
        env = load_env()

    apps_roots = resolve_scan_roots(env, cli_roots=roots)
    since_value = resolve_since(env, cli_since=since)
    codex_home = expand(env.get("CODEX_HOME", "~/.codex"))
    claude_home = expand(env.get("CLAUDE_HOME", "~/.claude"))
    required_roots = ", ".join(apps_roots)
    for key, val in (("APPS_DIR/APPS_DIRS", required_roots), ("CODEX_HOME", codex_home), ("CLAUDE_HOME", claude_home)):
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
    if since_value:
        print(f"  git since filter: {since_value}", flush=True)
    if refresh:
        print("  refresh: forcing phase1 cache rebuild", flush=True)
    t0 = time.monotonic()
    phase1_cmd = [sys.executable, str(SCRIPT_DIR / "phase1_runner.py")]
    if since_value:
        phase1_cmd.extend(["--since", since_value])
    if refresh:
        phase1_cmd.append("--refresh")
    for root in apps_roots:
        phase1_cmd.extend(["--root", root])
    result = subprocess.run(
        phase1_cmd,
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
        phase2_obj = parse_llm_json_output(report_text)
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
    insights_meta = parse_insights_sections(expanded_payload.get("insights", []), env)
    insights_quotes, _ = extract_insights_quote_entries(env, claude_bin=claude_bin)
    phase2_quotes = []
    if isinstance(sections.get("insights_quotes"), list):
        for item in sections.get("insights_quotes") or []:
            if not isinstance(item, dict):
                continue
            quote = (item.get("quote") or "").strip()
            if not quote:
                continue
            phase2_quotes.append(
                {
                    "quote": quote,
                    "source_path": item.get("source_path", ""),
                    "source_link": item.get("source_link", ""),
                    "section_id": item.get("section_id", ""),
                    "section_title": item.get("section_title", ""),
                }
            )
    merged_quotes: list[dict[str, str]] = []
    seen_quotes: set[str] = set()
    for item in phase2_quotes + insights_quotes:
        quote = (item.get("quote") or "").strip()
        if not quote or quote in seen_quotes:
            continue
        seen_quotes.add(quote)
        merged_quotes.append(item)

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
        "insights": {
            "source": insights_meta.get("source", {}),
            "sections": insights_meta.get("sections", []),
            "quotes": merged_quotes,
        },
        "render_hints": render_hints,
        "source_payload": compact_payload if include_source_payload else None,
    }

    # Optional local JSON edit pass before render (no extra model calls).
    if should_run_interactive(interactive):
        print("== Interactive review: phase 2 JSON edit/prune ==", flush=True)
        try:
            from review_report import run_interactive_review
            report_obj, changed = run_interactive_review(report_obj)
        except Exception as exc:
            print(f"  Interactive review unavailable: {exc}", file=sys.stderr)
            return 1
        if changed:
            print("  Interactive edits applied.", flush=True)
        else:
            print("  No interactive edits made.", flush=True)

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
    parser.add_argument("--interactive", action="store_true",
                        help="Prompt to edit/prune Phase 2 JSON before rendering")
    parser.add_argument("--since", help="Limit git activity to commits since this date/time.")
    parser.add_argument("--refresh", action="store_true", help="Force phase1 cache rebuild.")
    parser.add_argument("--root", action="append", default=[],
                        help="Project root directory to scan (repeatable).")
    args = parser.parse_args()

    if args.interactive and not args.foreground:
        print("Interactive mode requires foreground output; switching to --foreground.", flush=True)
        args.foreground = True

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
            child_cmd = [sys.executable, __file__, "--foreground"]
            if args.interactive:
                child_cmd.append("--interactive")
            if args.since:
                child_cmd.extend(["--since", args.since])
            if args.refresh:
                child_cmd.append("--refresh")
            for root in args.root:
                child_cmd.extend(["--root", root])
            proc = subprocess.Popen(
                child_cmd,
                stdout=lf,
                stderr=lf,
                start_new_session=True,
            )
        print(f"Pipeline started in background (PID {proc.pid}). Log: {log_file}", flush=True)
        return

    sys.exit(
        run(
            foreground=True,
            interactive=args.interactive,
            since=args.since,
            refresh=args.refresh,
            roots=args.root,
        )
    )


if __name__ == "__main__":
    main()
