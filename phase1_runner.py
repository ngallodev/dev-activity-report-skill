#!/usr/bin/env python3
"""Phase 1 data collector for dev-activity-report-skill, with caching.

This script prints one JSON object that has:
  {"fingerprint": <hash>, "cache_hit": bool, "data": {...}}

If nothing changed since the previous run, it exits after echoing the cached payload.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_FILE = SCRIPT_DIR / ".phase1-cache.json"
INSIGHTS_LOG = SCRIPT_DIR / "references" / "insights" / "insights-log.md"

DEFAULTS = {
    "APPS_DIR": "/lump/apps",
    "EXTRA_SCAN_DIRS": "/usr/local/lib/mariadb",
    "CODEX_HOME": "~/.codex",
    "CLAUDE_HOME": "~/.claude",
    "REPORT_OUTPUT_DIR": "~",
    "REPORT_FILENAME_PREFIX": "dev-activity-report",
    "RESUME_HEADER": "ngallodev Software, Jan 2025 – Present",
    "PHASE1_MODEL": "haiku",
    "PHASE3_MODEL": "gpt-5.1-codex-mini",
}

MARKERS = [".not-my-work", ".skip-for-now", ".forked-work", ".forked-work-modified"]
SNIPPET_LEN = 400
MAX_LOG_ENTRIES = 5
MAX_KEY_FILES = 6
MAX_CODEX_FILES = 5
MAX_FORKED_DIFFS = 10
MAX_EXTRA_LOG = 4
MAX_ACTIVE_CWDS = 20
MAX_SKILL_LIST = 40


def load_env() -> dict[str, str]:
    env_path = SCRIPT_DIR / ".env"
    fallback = Path("~/.claude/skills/dev-activity-report/.env").expanduser()
    if not env_path.exists() and fallback.exists():
        env_path = fallback
    parsed = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip()
    for key, default in DEFAULTS.items():
        parsed.setdefault(key, default)
    parsed.setdefault("SKILL_DIR", str(SCRIPT_DIR))
    return parsed


def expand_path(val: str) -> str:
    return os.path.abspath(os.path.expanduser(val))


def safe_stat(path: Path) -> int | None:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return None


def dir_fp(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    max_mtime = 0
    for root, dirs, files in os.walk(path):
        rel = os.path.relpath(root, path)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 3:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d != ".git" and not d.startswith(".")]
        for name in files:
            if name == ".dev-report-cache.md":
                continue
            try:
                full = Path(root) / name
                max_mtime = max(max_mtime, int(full.stat().st_mtime))
            except OSError:
                continue
    if max_mtime:
        return str(max_mtime)
    fallback = safe_stat(path)
    return str(fallback) if fallback else ""


def discover_markers(apps_dir: Path) -> tuple[list[dict[str, str]], set[str]]:
    markers = []
    skip = set()
    if not apps_dir.exists():
        return markers, skip
    for root, dirs, files in os.walk(apps_dir):
        rel = os.path.relpath(root, apps_dir)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 2:
            dirs[:] = []
            continue
        for marker in MARKERS:
            if marker in files:
                rel_path = Path(root).relative_to(apps_dir)
                project = rel_path.parts[0] if rel_path.parts else ""
                markers.append({
                    "marker": marker,
                    "path": str(Path(root).resolve()),
                    "project": project,
                })
                if marker in {".not-my-work", ".skip-for-now"}:
                    skip.add(str(Path(root).resolve()))
    return markers, skip


def is_under_skip(path: Path, skip: set[str]) -> bool:
    path_str = str(path.resolve())
    for skip_root in skip:
        if path_str == skip_root or path_str.startswith(skip_root + os.sep):
            return True
    return False


def read_cache_header(project_path: Path) -> str:
    cache_file = project_path / ".dev-report-cache.md"
    if not cache_file.exists():
        return ""
    try:
        with cache_file.open(encoding="utf-8", errors="ignore") as fh:
            return fh.readline().strip()
    except OSError:
        return ""


def collect_projects(apps_dir: Path, skip: set[str]) -> list[dict[str, str]]:
    projects = []
    if not apps_dir.exists():
        return projects
    for child in sorted(apps_dir.iterdir()):
        if not child.is_dir():
            continue
        if is_under_skip(child, skip):
            continue
        fingerprint = dir_fp(child)
        cache_header = read_cache_header(child)
        projects.append(
            {
                "name": child.name,
                "path": str(child.resolve()),
                "fingerprint": fingerprint,
                "cache_header": cache_header,
            }
        )
    return projects


def compute_fingerprint_source(
    projects: list[dict[str, str]],
    markers: list[dict[str, str]],
    extra_summaries: list[dict[str, str]],
    claude_meta: dict[str, str],
    codex_meta: dict[str, str],
    insights_mtime: int | None,
) -> dict[str, object]:
    marker_map: dict[str, list[str]] = {}
    for entry in markers:
        project = entry.get("project") or entry.get("path")
        if not project:
            continue
        marker_map.setdefault(project, []).append(entry["marker"])
    project_entries = []
    for proj in projects:
        entry = {
            "name": proj["name"],
            "fingerprint": proj["fingerprint"],
            "markers": sorted(marker_map.get(proj["name"], [])),
        }
        project_entries.append(entry)
    return {
        "projects": project_entries,
        "extra": [
            {"path": e["path"], "fingerprint": e.get("fingerprint","")}
            for e in extra_summaries
        ],
        "claude": claude_meta,
        "codex": codex_meta,
        "insights_mtime": insights_mtime or "",
    }


def hash_payload(obj: object) -> str:
    serialized = json.dumps(obj, sort_keys=True, separators=(",",":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def read_cache() -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(fingerprint: str, payload: dict[str, object]) -> None:
    entry = {
        "fingerprint": fingerprint,
        "cached_at": datetime.utcnow().isoformat(),
        "data": payload,
    }
    try:
        CACHE_FILE.write_text(json.dumps(entry, separators=(",",":"), ensure_ascii=False))
    except OSError:
        pass


def tail_lines(path: Path, limit: int = 60) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            dq = deque(maxlen=limit)
            for line in fh:
                dq.append(line.rstrip())
            return list(dq)
    except OSError:
        return []


def run_command(cwd: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            env=os.environ,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def run_git_log(path: Path, max_entries: int = MAX_LOG_ENTRIES) -> list[str]:
    output = run_command(path, ["git", "-C", str(path), "log", f"--oneline", f"-n", str(max_entries)])
    return [line for line in output.splitlines() if line][:max_entries]


def run_git_diff_names(path: Path, max_entries: int = MAX_FORKED_DIFFS) -> list[str]:
    output = run_command(
        path,
        ["git", "-C", str(path), "diff", "HEAD~10..HEAD", "--name-only"],
    )
    return [line for line in output.splitlines() if line][:max_entries]


def collect_key_files(path: Path) -> list[str]:
    matches: list[str] = []
    patterns = ["*.md", "*.csproj", "Dockerfile*", "docker-compose*.yml"]
    for root, dirs, files in os.walk(path):
        rel = os.path.relpath(root, path)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 3:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d != ".git" and not d.startswith(".")]
        for name in files:
            if len(matches) >= MAX_KEY_FILES:
                break
            for pat in patterns:
                if fnmatch.fnmatch(name, pat):
                    rel_path = os.path.relpath(Path(root) / name, path)
                    matches.append(rel_path)
                    break
        if len(matches) >= MAX_KEY_FILES:
            break
    return matches


def collect_codex_files(path: Path) -> list[str]:
    matches = []
    targets = {"AGENTS.md", "codex.md", ".codex"}
    for root, dirs, files in os.walk(path):
        rel = os.path.relpath(root, path)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 3:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if len(matches) >= MAX_CODEX_FILES:
                break
            if name in targets:
                matches.append(os.path.relpath(Path(root) / name, path))
        if len(matches) >= MAX_CODEX_FILES:
            break
    return matches


def read_snippet(path: Path, length: int = SNIPPET_LEN) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:length]
        if len(text) == length:
            return text.rstrip() + "…"
        return text.rstrip()
    except OSError:
        return ""


def find_recent_files(path: Path, limit: int = 8) -> list[str]:
    reference = path / "README.md"
    ref_time = safe_stat(reference) or 0
    collected = []
    for root, dirs, files in os.walk(path):
        rel = os.path.relpath(root, path)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 2:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d != ".git" and not d.startswith(".")]
        for name in sorted(files):
            if len(collected) >= limit:
                break
            full = Path(root) / name
            try:
                if ref_time and int(full.stat().st_mtime) <= ref_time:
                    continue
            except OSError:
                continue
            collected.append(os.path.relpath(full, path))
        if len(collected) >= limit:
            break
    return collected


def summarize_forked_modified(path: Path, apps_dir: Path) -> dict[str, object]:
    return {
        "project": _project_name(path, apps_dir),
        "path": str(path),
        "git_log": run_git_log(path, max_entries=10),
        "diff_files": run_git_diff_names(path, max_entries=MAX_FORKED_DIFFS),
        "recent_files": find_recent_files(path, limit=8),
    }


def _project_name(path: Path, apps_dir: Path) -> str:
    try:
        rel = path.relative_to(apps_dir)
    except ValueError:
        return path.name
    return rel.parts[0] if rel.parts else path.name


def collect_extra_location(path: Path) -> dict[str, object]:
    info: dict[str, object] = {"path": str(path)}
    info["exists"] = path.exists()
    if not path.exists():
        return info
    fp = dir_fp(path)
    info["fingerprint"] = fp
    cache_header = read_cache_header(path)
    info["cache_header"] = cache_header
    info["cache_hit"] = bool(fp and cache_header and fp in cache_header)
    info["git_log"] = run_git_log(path, max_entries=MAX_EXTRA_LOG)
    info["snippet"] = read_snippet(path / "README.md", length=250)
    return info


def collect_claude_activity(claude_home: Path) -> tuple[dict[str, object], dict[str, str | int]]:
    summary = {}
    meta: dict[str, str | int] = {}
    for label in ("skills", "hooks", os.path.join("agents", "team")):
        key = f"{label.replace(os.sep, "_")}_list"
        candidate = claude_home / label
        summary[key] = list_dir(candidate, limit=MAX_SKILL_LIST)
    metrics = claude_home / "delegation-metrics.jsonl"
    summary["delegation_metrics_head"] = head_lines(metrics, 2)
    summary["delegation_metrics"] = "exists" if metrics.exists() else "missing"
    meta["delegation_mtime"] = safe_stat(metrics) or ""
    meta["skills_mtime"] = safe_stat(claude_home / "skills") or ""
    meta["hooks_mtime"] = safe_stat(claude_home / "hooks") or ""
    meta["agents_mtime"] = safe_stat(claude_home / "agents") or ""
    return summary, meta


def list_dir(path: Path, limit: int = 20) -> list[str]:
    if not path.exists():
        return []
    try:
        return [str(child.name) for child in sorted(path.iterdir())[:limit]]
    except OSError:
        return []


def head_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            lines = []
            for _ in range(limit):
                line = fh.readline()
                if not line:
                    break
                lines.append(line.rstrip())
            return lines
    except OSError:
        return []


def collect_codex_activity(codex_home: Path) -> tuple[dict[str, object], dict[str, str | int]]:
    summary: dict[str, object] = {}
    meta: dict[str, str | int] = {}
    sessions_dir = codex_home / "sessions"
    sessions_mtime = safe_stat(sessions_dir) or 0
    meta["sessions_mtime"] = sessions_mtime
    summary["fingerprint"] = sessions_mtime
    config_file = codex_home / "config.toml"
    if config_file.exists():
        summary["config"] = read_snippet(config_file, length=600)
    skills_dir = codex_home / "skills"
    summary["skills"] = list_dir(skills_dir, limit=MAX_SKILL_LIST)
    meta["skills_mtime"] = safe_stat(skills_dir) or ""
    months: dict[str, int] = {}
    cwds: set[str] = set()
    session_files = []
    if sessions_dir.exists():
        for sf in sessions_dir.rglob("*.jsonl"):
            session_files.append(sf)
        session_files.sort()
    for session in session_files[-50:]:
        parts = session.parts
        if len(parts) >= 4:
            month = f"{parts[-4]}-{parts[-3]}"
            months[month] = months.get(month, 0) + 1
        try:
            with session.open(encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "environment_context" in line:
                        start = line.find("<cwd>")
                        end = line.find("</cwd>")
                        if start != -1 and end != -1:
                            cwds.add(line[start + 5 : end])
        except OSError:
            continue
    summary["sessions_by_month"] = dict(sorted(months.items()))
    summary["active_cwds"] = sorted(list(cwds))[:MAX_ACTIVE_CWDS]
    rules_file = codex_home / "rules" / "default.rules"
    summary["rules_count"] = count_lines(rules_file)
    meta["rules_mtime"] = safe_stat(rules_file) or ""
    return summary, meta


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def build_stale_projects(projects: list[dict[str, str]], apps_dir: Path) -> list[dict[str, object]]:
    stale: list[dict[str, object]] = []
    for entry in projects:
        fp = entry.get("fingerprint")
        cache_header = entry.get("cache_header") or ""
        if fp and cache_header and fp in cache_header:
            continue
        path = Path(entry["path"])
        stale.append(
            {
                "project": entry["name"],
                "path": entry["path"],
                "fingerprint": fp,
                "cache_header": cache_header,
                "mtime": safe_stat(path) or "",
                "git_log": run_git_log(path),
                "key_files": collect_key_files(path),
                "codex_files": collect_codex_files(path),
                "snippets": {
                    fname: read_snippet(path / fname)
                    for fname in ["README.md", "AGENTS.md", ".claude/plan.md", ".forked-work"]
                    if (path / fname).exists()
                },
            }
        )
    return stale


def main() -> None:
    env = load_env()
    apps_dir = Path(expand_path(env["APPS_DIR"]))
    extra_dirs = [Path(expand_path(p)) for p in env.get("EXTRA_SCAN_DIRS", "").split() if p]
    claude_home = Path(expand_path(env.get("CLAUDE_HOME", "~/.claude")))
    codex_home = Path(expand_path(env.get("CODEX_HOME", "~/.codex")))

    markers, skip_dirs = discover_markers(apps_dir)
    projects = collect_projects(apps_dir, skip_dirs)

    extra_summaries = [collect_extra_location(d) for d in extra_dirs]
    claude_payload, claude_meta = collect_claude_activity(claude_home)
    codex_payload, codex_meta = collect_codex_activity(codex_home)
    insights_lines = tail_lines(INSIGHTS_LOG, limit=60)
    insights_mtime = safe_stat(INSIGHTS_LOG)

    fingerprint_source = compute_fingerprint_source(
        projects, markers, extra_summaries, claude_meta, codex_meta, insights_mtime
    )
    fingerprint = hash_payload(fingerprint_source)

    cache = read_cache()
    if cache and cache.get("fingerprint") == fingerprint:
        payload = cache.get("data", {})
        print(json.dumps({"fingerprint": fingerprint, "cache_hit": True, "data": payload}, separators=(",",":"), ensure_ascii=False))
        return

    stale_projects = build_stale_projects(projects, apps_dir)
    forked = []
    seen: set[str] = set()
    for marker in markers:
        if marker["marker"] != ".forked-work-modified":
            continue
        path = Path(marker["path"])
        if not path.exists():
            continue
        if str(path) in seen:
            continue
        seen.add(str(path))
        forked.append(summarize_forked_modified(path, apps_dir))

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "apps_dir": str(apps_dir),
        "ownership_markers": markers,
        "cache_fingerprints": projects,
        "stale_projects": stale_projects,
        "forked_work_modified": forked,
        "extra_locations": extra_summaries,
        "claude_activity": claude_payload,
        "insights_log": insights_lines,
        "codex_activity": codex_payload,
    }

    write_cache(fingerprint, payload)
    print(json.dumps({"fingerprint": fingerprint, "cache_hit": False, "data": payload}, separators=(",",":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
