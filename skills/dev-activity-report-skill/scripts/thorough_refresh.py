#!/usr/bin/env python3
"""Thorough refresh utility for dev-activity-report.

Purpose:
- Clear caches across configured app roots and skill locations
- Normalize fork markers to force fork re-attribution
- Optionally clear exclusion markers for full re-evaluation runs

Usage:
  python3 thorough_refresh.py
  python3 thorough_refresh.py --confirm
  python3 thorough_refresh.py --confirm --clear-skip --clear-not-my-work-all
  python3 thorough_refresh.py --confirm --root /lump/apps --root /lump/other
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import dotenv_values  # type: ignore
except ImportError:  # pragma: no cover
    dotenv_values = None


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def expand_path(value: str) -> Path:
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(value))))


def parse_paths(raw: str) -> list[Path]:
    parts = [p for p in raw.replace(",", " ").split() if p.strip()]
    return [expand_path(p) for p in parts]


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    if dotenv_values:
        env.update({k: v for k, v in dotenv_values(path).items() if v is not None})
        return env
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k, v = stripped.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def load_env() -> dict[str, str]:
    env = load_env_file(SKILL_DIR / ".env")
    claude_home = expand_path(env.get("CLAUDE_HOME", "~/.claude"))
    installed_env = claude_home / "skills" / "dev-activity-report" / ".env"
    if not installed_env.exists():
        installed_env = claude_home / "skills" / "dev-activity-report-skill" / ".env"
    installed = load_env_file(installed_env)
    # Local skill .env takes precedence, then installed .env.
    merged = installed
    merged.update(env)
    return merged


def unique_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def resolve_roots(env: dict[str, str], cli_roots: list[str]) -> list[Path]:
    if cli_roots:
        return unique_paths([expand_path(r) for r in cli_roots if r.strip()])
    roots = parse_paths(env.get("APPS_DIRS", ""))
    if roots:
        return unique_paths(roots)
    return [expand_path(env.get("APPS_DIR", "~/projects"))]


@dataclass
class Plan:
    delete_files: list[Path] = field(default_factory=list)
    touch_files: list[Path] = field(default_factory=list)
    stats: dict[str, int] = field(
        default_factory=lambda: {
            "cache_files": 0,
            "promote_forked": 0,
            "clear_not_my_work_forked": 0,
            "clear_not_my_work_all": 0,
            "clear_skip": 0,
        }
    )

    def add_delete(self, path: Path, stat_key: str | None = None) -> None:
        if path.exists() and path not in self.delete_files:
            self.delete_files.append(path)
            if stat_key:
                self.stats[stat_key] += 1

    def add_touch(self, path: Path, stat_key: str | None = None) -> None:
        if not path.exists() and path not in self.touch_files:
            self.touch_files.append(path)
            if stat_key:
                self.stats[stat_key] += 1


def collect_skill_cache_targets(plan: Plan, skill_root: Path) -> None:
    for name in (".phase1-cache.json", ".phase1-cache.tmp", ".dev-report-cache.md"):
        for folder in (skill_root, skill_root / "scripts"):
            plan.add_delete(folder / name, "cache_files")


def collect_root_cache_targets(plan: Plan, root: Path) -> None:
    if not root.exists():
        return
    for project in sorted(root.iterdir()):
        if not project.is_dir():
            continue
        plan.add_delete(project / ".dev-report-cache.md", "cache_files")


def collect_marker_actions(
    plan: Plan,
    roots: list[Path],
    clear_skip: bool,
    clear_not_my_work_all: bool,
    clear_not_my_work_forked: bool,
) -> None:
    for root in roots:
        if not root.exists():
            continue
        for project in sorted(root.iterdir()):
            if not project.is_dir():
                continue
            forked = project / ".forked-work"
            forked_mod = project / ".forked-work-modified"
            not_mine = project / ".not-my-work"
            skip = project / ".skip-for-now"

            if forked.exists() and not forked_mod.exists():
                plan.add_touch(forked_mod, "promote_forked")

            if clear_not_my_work_all:
                plan.add_delete(not_mine, "clear_not_my_work_all")
            elif clear_not_my_work_forked and (forked.exists() or forked_mod.exists()):
                plan.add_delete(not_mine, "clear_not_my_work_forked")

            if clear_skip:
                plan.add_delete(skip, "clear_skip")


def apply_plan(plan: Plan, confirm: bool) -> None:
    for path in sorted(plan.delete_files):
        action = "DELETE" if confirm else "DRY-DELETE"
        print(f"{action}: {path}")
        if confirm:
            try:
                path.unlink()
            except OSError as exc:
                print(f"  warning: failed to delete {path}: {exc}")
    for path in sorted(plan.touch_files):
        action = "TOUCH" if confirm else "DRY-TOUCH"
        print(f"{action}: {path}")
        if confirm:
            try:
                path.touch(exist_ok=True)
            except OSError as exc:
                print(f"  warning: failed to touch {path}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Thorough refresh/reset for dev-activity-report.")
    parser.add_argument("--confirm", action="store_true", help="Apply changes. Without this flag, dry-run only.")
    parser.add_argument("--root", action="append", default=[], help="Scan root (repeatable). Overrides APPS_DIR/APPS_DIRS.")
    parser.add_argument(
        "--clear-skip",
        action="store_true",
        help="Remove .skip-for-now markers so skipped repos are re-evaluated.",
    )
    parser.add_argument(
        "--clear-not-my-work-all",
        action="store_true",
        help="Remove .not-my-work markers from all project dirs in roots.",
    )
    parser.add_argument(
        "--keep-not-my-work-on-forks",
        action="store_true",
        help="Do not remove .not-my-work even when fork markers exist.",
    )
    args = parser.parse_args()

    env = load_env()
    roots = resolve_roots(env, args.root)
    claude_home = expand_path(env.get("CLAUDE_HOME", "~/.claude"))
    codex_home = expand_path(env.get("CODEX_HOME", "~/.codex"))
    installed_skill = claude_home / "skills" / "dev-activity-report"
    legacy_installed_skill = claude_home / "skills" / "dev-activity-report-skill"

    plan = Plan()

    # Skill-local and installed-skill caches.
    collect_skill_cache_targets(plan, SKILL_DIR)
    collect_skill_cache_targets(plan, installed_skill)
    collect_skill_cache_targets(plan, legacy_installed_skill)

    # Home-level codex cache used by this application.
    plan.add_delete(codex_home / ".dev-report-cache.md", "cache_files")

    # Per-project caches.
    for root in roots:
        collect_root_cache_targets(plan, root)

    collect_marker_actions(
        plan=plan,
        roots=roots,
        clear_skip=args.clear_skip,
        clear_not_my_work_all=args.clear_not_my_work_all,
        clear_not_my_work_forked=not args.keep_not_my_work_on_forks,
    )

    print("Resolved roots:")
    for root in roots:
        print(f"  - {root}")
    print(f"Claude home: {claude_home}")
    print(f"Codex home:  {codex_home}")
    print(f"Mode: {'APPLY' if args.confirm else 'DRY-RUN'}")
    print("")

    apply_plan(plan, confirm=args.confirm)

    print("")
    print("Summary:")
    for key in (
        "cache_files",
        "promote_forked",
        "clear_not_my_work_forked",
        "clear_not_my_work_all",
        "clear_skip",
    ):
        print(f"  {key}: {plan.stats[key]}")
    print(f"  total_deletes: {len(plan.delete_files)}")
    print(f"  total_touches: {len(plan.touch_files)}")
    if not args.confirm:
        print("")
        print("Dry-run only. Re-run with --confirm to apply.")


if __name__ == "__main__":
    main()
