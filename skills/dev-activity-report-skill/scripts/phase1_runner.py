#!/usr/bin/env python3
"""Phase 1 data collector — compact payload + content-hash fingerprinting."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

try:
    from dotenv import dotenv_values  # type: ignore
except ImportError:  # pragma: no cover
    dotenv_values = None

try:
    import pygit2  # type: ignore
except ImportError:  # pragma: no cover
    pygit2 = None

SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = SKILL_DIR / ".phase1-cache.json"
INSIGHTS_LOG = SKILL_DIR / "references" / "examples" / "insights" / "insights-log.md"
FP_IGNORE_FILE = SKILL_DIR / ".dev-report-fingerprint-ignore"


def load_fp_ignore_patterns() -> list[str]:
    """Load glob patterns from .dev-report-fingerprint-ignore (one per line, # comments ok)."""
    if not FP_IGNORE_FILE.exists():
        return []
    patterns = []
    for line in FP_IGNORE_FILE.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return patterns


def _matches_ignore(rel_path: str, patterns: list[str]) -> bool:
    """Return True if rel_path matches any ignore glob pattern.

    Supports:
    - Standard fnmatch against the full relative path
    - fnmatch against the filename alone
    - Directory prefix: pattern ending with '/*' is treated as a prefix match
      so 'todos/*' matches 'todos/uuid/1.json' at any depth.
    """
    rel_posix = rel_path.replace(os.sep, "/")
    name = Path(rel_path).name
    for pat in patterns:
        if fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(name, pat):
            return True
        # Treat "dir/*" as a recursive prefix: anything under "dir/"
        if pat.endswith("/*"):
            prefix = pat[:-2]  # strip trailing /*
            if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
                return True
    return False

DEFAULTS: dict[str, str] = {
    "APPS_DIR": "/lump/apps",
    "EXTRA_SCAN_DIRS": "/usr/local/lib/mariadb",
    "CODEX_HOME": "~/.codex",
    "CLAUDE_HOME": "~/.claude",
    "REPORT_OUTPUT_DIR": "~",
    "REPORT_FILENAME_PREFIX": "dev-activity-report",
    "RESUME_HEADER": "ngallodev Software, Jan 2025 – Present",
    "PHASE1_MODEL": "haiku",
    "PHASE15_MODEL": "haiku",
    "PHASE2_MODEL": "sonnet",
    "PHASE3_MODEL": "gpt-5.1-codex-mini",
    "ALLOWED_FILE_EXTS": ".py,.ts,.js,.tsx,.cs,.csproj,.md,.txt,.json,.toml,.yaml,.yml,.sql,.html,.css,.sh",
    "INSIGHTS_REPORT_PATH": "~/.claude/usage-data/report.html",
}

MARKERS = [".not-my-work", ".skip-for-now", ".forked-work", ".forked-work-modified"]
IGNORED_DIRS = {".git", "node_modules", "venv", "bin", "obj", ".cache", "__pycache__"}
MAX_INSIGHTS_LINES = 24
MAX_CHANGED_FILES = 10
MAX_COMMIT_MESSAGES = 6
MAX_KEY_FILES = 6
MAX_ACTIVE_CWDS = 20
MAX_HASH_FILE_SIZE = 100 * 1024 * 1024  # 100 MB — skip content hash for files larger than this


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = SKILL_DIR / ".env"
    if dotenv_values and env_path.exists():
        env.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    elif env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for key, default in DEFAULTS.items():
        env.setdefault(key, default)
    env.setdefault("SKILL_DIR", str(SKILL_DIR))
    return env


def expand_path(val: str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(val)))


def parse_exts(raw: str) -> set[str]:
    return {
        e.strip().lower() if e.strip().startswith(".") else f".{e.strip().lower()}"
        for e in raw.split(",")
        if e.strip()
    }


def parse_paths(raw: str) -> list[Path]:
    parts = [p for p in raw.replace(",", " ").split() if p]
    return [expand_path(p) for p in parts]


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        if path.stat().st_size > MAX_HASH_FILE_SIZE:
            return hashlib.sha256(b"LARGE_FILE:" + str(path).encode()).hexdigest()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def hash_paths(base: Path, files: Sequence[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode())
        full = base / rel
        if full.is_file():
            try:
                if full.stat().st_size > MAX_HASH_FILE_SIZE:
                    h.update(b"LARGE_FILE")
                    continue
                with full.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
            except OSError:
                continue
    return h.hexdigest()


def git_tracked_files(path: Path) -> list[str]:
    if pygit2 is not None:
        try:
            repo = pygit2.Repository(str(path))
            repo.index.read()
            return [entry.path for entry in repo.index]
        except Exception as exc:  # pygit2.GitError or similar
            print(f"warning: pygit2 index read failed for {path}: {exc}", file=sys.stderr)
            return []
    # fallback: subprocess
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "ls-files", "-z"],
            capture_output=True,
            text=False,
            check=False,
            env=os.environ,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            if stderr:
                print(f"warning: git ls-files failed for {path}: {stderr}", file=sys.stderr)
            return []
        return [p for p in result.stdout.decode("utf-8", errors="ignore").split("\0") if p]
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"warning: git ls-files error for {path}: {exc}", file=sys.stderr)
        return []


def is_git_repo(path: Path) -> bool:
    if pygit2 is not None:
        try:
            pygit2.discover_repository(str(path))
            return True
        except Exception:
            return False
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def git_head(path: Path) -> str:
    if pygit2 is not None:
        try:
            repo = pygit2.Repository(str(path))
            return str(repo.head.target)
        except Exception:
            return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def hash_git_repo(path: Path) -> str:
    files = git_tracked_files(path)
    ignore = load_fp_ignore_patterns()
    if ignore:
        files = [f for f in files if not _matches_ignore(f, ignore)]
    return hash_paths(path, files)


def hash_non_git_dir(path: Path, allowed_exts: set[str], max_depth: int = 4) -> str:
    selected: list[str] = []
    if not path.exists():
        return ""
    for root, dirs, files in os.walk(path):
        rel_root = os.path.relpath(root, path)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        ignore = load_fp_ignore_patterns()
        for name in files:
            suffix = Path(name).suffix.lower()
            if suffix not in allowed_exts:
                continue
            rel_path = os.path.relpath(Path(root) / name, path)
            if ignore and _matches_ignore(rel_path, ignore):
                continue
            selected.append(rel_path)
    return hash_paths(path, selected)


def safe_stat(path: Path) -> int | None:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return None


def discover_markers(apps_dir: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    markers = []
    project_status: dict[str, str] = {}
    if not apps_dir.exists():
        return markers, project_status
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
                markers.append({"m": marker, "p": project, "path": str(Path(root).resolve())})
                if marker == ".not-my-work":
                    project_status[project] = "not"
                elif marker == ".skip-for-now":
                    project_status[project] = "skip"
                elif marker == ".forked-work":
                    project_status.setdefault(project, "fork")
                elif marker == ".forked-work-modified":
                    project_status[project] = "fork_mod"
    return markers, project_status


def parse_cached_fp(cache_header: str) -> str:
    match = re.search(r"fingerprint:\s*([a-f0-9]+)", cache_header)
    return match.group(1) if match else ""


def read_cache_header(project_path: Path) -> str:
    cache_file = project_path / ".dev-report-cache.md"
    if not cache_file.exists():
        return ""
    try:
        with cache_file.open(encoding="utf-8", errors="ignore") as fh:
            return fh.readline().strip()
    except OSError:
        return ""


def collect_projects(apps_dir: Path, status_map: dict[str, str], allowed_exts: set[str]) -> list[dict[str, object]]:
    projects: list[dict[str, object]] = []
    if not apps_dir.exists():
        return projects
    for child in sorted(apps_dir.iterdir()):
        if not child.is_dir():
            continue
        project_status = status_map.get(child.name, "orig")
        if project_status in {"not", "skip"}:
            continue
        git_repo = is_git_repo(child)
        fingerprint = hash_git_repo(child) if git_repo else hash_non_git_dir(child, allowed_exts)
        head = git_head(child) if git_repo else ""
        cache_header = read_cache_header(child)
        cached_fp = parse_cached_fp(cache_header)
        cache_hit = bool(fingerprint and cached_fp and fingerprint == cached_fp)
        projects.append(
            {
                "name": child.name,
                "path": str(child.resolve()),
                "fp": fingerprint,
                "head": head,
                "cached_fp": cached_fp,
                "cache_hit": cache_hit,
                "status": project_status,
                "git": git_repo,
            }
        )
    return projects


def run_command(args: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            env=os.environ,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git_range_base(project: dict[str, object]) -> str:
    # cached_fp is now a content hash (SHA-256), not a git ref — never use it as a base.
    head = project.get("head", "") or ""
    if head:
        return f"{head}~20"
    return "HEAD~20"


def git_commit_count(path: Path, base: str) -> int:
    output = run_command(["git", "-C", str(path), "rev-list", "--count", f"{base}..HEAD"])
    try:
        return int(output.strip() or 0)
    except ValueError:
        return 0


def git_shortstat(path: Path, base: str) -> str:
    return run_command(["git", "-C", str(path), "diff", f"{base}..HEAD", "--shortstat"])


def git_changed_files(path: Path, base: str, limit: int = MAX_CHANGED_FILES) -> list[str]:
    output = run_command(["git", "-C", str(path), "diff", f"{base}..HEAD", "--name-only"])
    files = [line for line in output.splitlines() if line][:limit]
    return files


def git_messages(path: Path, base: str, limit: int = MAX_COMMIT_MESSAGES) -> list[str]:
    output = run_command(
        ["git", "-C", str(path), "log", f"{base}..HEAD", "--format=%s", f"-n{limit}"]
    )
    return [line for line in output.splitlines() if line][:limit]


def derive_highlights(messages: Sequence[str], files: Sequence[str]) -> list[str]:
    themes = []
    joined = " ".join(messages).lower()
    if any(k in joined for k in ("perf", "speed", "latency", "optimiz")):
        themes.append("perf")
    if any(k in joined for k in ("refactor", "cleanup", "rewrite")):
        themes.append("refactor")
    if any(k in joined for k in ("fix", "bug", "patch", "hotfix")):
        themes.append("bugfix")
    if any(k in joined for k in ("doc", "readme", "comment")):
        themes.append("docs")
    if any(k in joined for k in ("deps", "bump", "upgrade", "package")) or any(
        "package" in f or "requirements" in f or "poetry.lock" in f or "package-lock" in f for f in files
    ):
        themes.append("deps")
    if any(k in joined for k in ("ai", "prompt", "model", "llm")):
        themes.append("ai-workflow")
    return themes[:4]


def collect_key_files(path: Path, patterns: Iterable[str] = ("*.md", "*.csproj", "Dockerfile*", "docker-compose*.yml")) -> list[str]:
    matches: list[str] = []
    for root, dirs, files in os.walk(path):
        rel = os.path.relpath(root, path)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 3:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
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


def summarize_project(entry: dict[str, object]) -> dict[str, object]:
    path = Path(entry["path"])
    status = entry.get("status", "orig")
    base = git_range_base(entry)
    if entry.get("git"):
        commit_count = git_commit_count(path, base)
        shortstat = git_shortstat(path, base)
        files = git_changed_files(path, base)
        messages = git_messages(path, base)
    else:
        commit_count = 0
        shortstat = ""
        files = collect_key_files(path)
        messages = []
    highlights = derive_highlights(messages, files)
    return {
        "n": entry["name"],
        "pt": entry["path"],
        "fp": entry.get("fp", ""),
        "st": status,
        "cc": commit_count,
        "sd": shortstat,
        "fc": files,
        "msg": messages,
        "hl": highlights,
    }


def collect_extra_location(path: Path, allowed_exts: set[str]) -> dict[str, object]:
    info: dict[str, object] = {"p": str(path)}
    info["exists"] = path.exists()
    if not path.exists():
        return info
    git_repo = is_git_repo(path)
    info["git"] = git_repo
    info["fp"] = hash_git_repo(path) if git_repo else hash_non_git_dir(path, allowed_exts)
    info["kf"] = collect_key_files(path)
    return info


def tail_lines(path: Path, limit: int = MAX_INSIGHTS_LINES) -> list[str]:
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


def collect_insights_log(env: dict[str, str]) -> tuple[list[str], str]:
    insights_lines = tail_lines(INSIGHTS_LOG, limit=MAX_INSIGHTS_LINES)
    insights_fp = hash_file(INSIGHTS_LOG) if INSIGHTS_LOG.exists() else ""
    report_path = expand_path(env.get("INSIGHTS_REPORT_PATH", ""))
    if report_path.exists():
        report_hash = hash_file(report_path)
        insights_fp = hashlib.sha256((insights_fp + report_hash).encode()).hexdigest()
    return insights_lines, insights_fp


def list_dir(path: Path, limit: int = 20) -> list[str]:
    if not path.exists():
        return []
    try:
        return [str(child.name) for child in sorted(path.iterdir())[:limit]]
    except OSError:
        return []


def collect_claude_activity(claude_home: Path, allowed_exts: set[str]) -> tuple[dict[str, object], dict[str, object]]:
    summary: dict[str, object] = {}
    meta: dict[str, object] = {}
    summary["sk"] = list_dir(claude_home / "skills", limit=20)
    summary["hk"] = list_dir(claude_home / "hooks", limit=20)
    summary["ag"] = list_dir(claude_home / "agents" / "team", limit=10)
    metrics = claude_home / "delegation-metrics.jsonl"
    meta["fp"] = hash_non_git_dir(claude_home, allowed_exts, max_depth=2)
    meta["metrics_head"] = tail_lines(metrics, limit=2)
    return summary, meta


def collect_codex_activity(codex_home: Path, allowed_exts: set[str]) -> tuple[dict[str, object], dict[str, object]]:
    summary: dict[str, object] = {}
    meta: dict[str, object] = {}
    sessions_dir = codex_home / "sessions"
    session_files = []
    if sessions_dir.exists():
        for sf in sessions_dir.rglob("*.jsonl"):
            session_files.append(sf)
        session_files.sort()
    session_files = session_files[-50:]
    months: dict[str, int] = {}
    cwds: set[str] = set()
    for session in session_files:
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
    summary["sm"] = dict(sorted(months.items()))
    summary["cw"] = sorted(list(cwds))[:MAX_ACTIVE_CWDS]
    config_file = codex_home / "config.toml"
    if config_file.exists():
        summary["md"] = "codex-config"
    skills_dir = codex_home / "skills"
    summary["sk"] = list_dir(skills_dir, limit=20)
    tracked_files = [str(sf.relative_to(codex_home)) for sf in session_files]
    meta["fp"] = hash_paths(codex_home, tracked_files)
    rules_file = codex_home / "rules" / "default.rules"
    meta["rules_lines"] = safe_stat(rules_file) or 0
    return summary, meta


def compute_fingerprint_source(
    projects: list[dict[str, object]],
    markers: list[dict[str, str]],
    extra_summaries: list[dict[str, object]],
    claude_meta: dict[str, object],
    codex_meta: dict[str, object],
    insights_fp: str,
) -> dict[str, object]:
    marker_map: dict[str, list[str]] = {}
    for entry in markers:
        project = entry.get("p") or entry.get("path")
        if not project:
            continue
        marker_map.setdefault(project, []).append(entry["m"])
    project_entries = []
    for proj in projects:
        entry = {
            "n": proj["name"],
            "fp": proj["fp"],
            "st": proj.get("status", "orig"),
            "m": sorted(marker_map.get(proj["name"], [])),
        }
        project_entries.append(entry)
    return {
        "projects": project_entries,
        "extra": [{"p": e.get("p") or e.get("path"), "fp": e.get("fp", "")} for e in extra_summaries],
        "claude_fp": claude_meta.get("fp", ""),
        "codex_fp": codex_meta.get("fp", ""),
        "insights_fp": insights_fp,
    }


def hash_payload(obj: object) -> str:
    serialized = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
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
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    tmp = CACHE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
        tmp.replace(CACHE_FILE)  # atomic on POSIX
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def build_payload(
    timestamp: str,
    apps_dir: Path,
    markers: list[dict[str, str]],
    projects: list[dict[str, object]],
    stale_projects: list[dict[str, object]],
    extra_summaries: list[dict[str, object]],
    claude_payload: dict[str, object],
    codex_payload: dict[str, object],
    insights_lines: list[str],
) -> dict[str, object]:
    marker_compact = [{"m": m["m"], "p": m["p"]} for m in markers]
    return {
        "ts": timestamp,
        "ad": str(apps_dir),
        "mk": marker_compact,
        "p": stale_projects,
        "x": extra_summaries,
        "cl": claude_payload,
        "cx": codex_payload,
        "ins": insights_lines,
        "stats": {
            "total": len(projects),
            "stale": len(stale_projects),
            "cached": len([p for p in projects if p.get("cache_hit")]),
        },
    }


def main() -> None:
    env = load_env()
    allowed_exts = parse_exts(env.get("ALLOWED_FILE_EXTS", DEFAULTS["ALLOWED_FILE_EXTS"]))

    apps_dir = expand_path(env["APPS_DIR"])
    extra_dirs = parse_paths(env.get("EXTRA_SCAN_DIRS", ""))
    claude_home = expand_path(env.get("CLAUDE_HOME", "~/.claude"))
    codex_home = expand_path(env.get("CODEX_HOME", "~/.codex"))

    markers, status_map = discover_markers(apps_dir)
    projects = collect_projects(apps_dir, status_map, allowed_exts)

    extra_summaries = [collect_extra_location(d, allowed_exts) for d in extra_dirs]
    claude_payload, claude_meta = collect_claude_activity(claude_home, allowed_exts)
    codex_payload, codex_meta = collect_codex_activity(codex_home, allowed_exts)
    insights_lines, insights_fp = collect_insights_log(env)

    fingerprint_source = compute_fingerprint_source(
        projects, markers, extra_summaries, claude_meta, codex_meta, insights_fp
    )
    fingerprint = hash_payload(fingerprint_source)

    cache = read_cache()
    if cache and cache.get("fingerprint") == fingerprint:
        payload = cache.get("data", {})
        print(json.dumps({"fp": fingerprint, "cache_hit": True, "data": payload}, separators=(",", ":"), ensure_ascii=False))
        return

    stale_projects = [summarize_project(p) for p in projects if not p.get("cache_hit")]

    payload = build_payload(
        timestamp=datetime.now(timezone.utc).isoformat(),
        apps_dir=apps_dir,
        markers=markers,
        projects=projects,
        stale_projects=stale_projects,
        extra_summaries=extra_summaries,
        claude_payload=claude_payload,
        codex_payload=codex_payload,
        insights_lines=insights_lines,
    )

    write_cache(fingerprint, payload)
    print(json.dumps({"fp": fingerprint, "cache_hit": False, "data": payload}, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
