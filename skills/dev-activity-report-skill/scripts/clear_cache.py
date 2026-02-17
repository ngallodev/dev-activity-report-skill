#!/usr/bin/env python3
"""Clear phase1 and per-project caches to force a full fresh scan on next run.

Usage:
    python3 clear_cache.py           # dry-run: show what would be removed
    python3 clear_cache.py --confirm # actually delete cache files
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from dotenv import dotenv_values  # type: ignore
except ImportError:
    dotenv_values = None

SKILL_DIR = Path(__file__).resolve().parent.parent
APPS_DIR_DEFAULT = "~/projects"


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
    return env


def expand(val: str) -> Path:
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(val))))


def collect_cache_files(apps_dir: Path) -> list[Path]:
    targets: list[Path] = []

    # Global phase1 cache (and any leftover .tmp from interrupted write)
    # Also sweep scripts/ in case the cache was written there by an earlier run
    for search_dir in (SKILL_DIR, SKILL_DIR / "scripts"):
        for name in (".phase1-cache.json", ".phase1-cache.tmp"):
            p = search_dir / name
            if p.exists() and p not in targets:
                targets.append(p)

    # Per-project caches under APPS_DIR (depth 1 only)
    if apps_dir.exists():
        for child in sorted(apps_dir.iterdir()):
            if not child.is_dir():
                continue
            cache = child / ".dev-report-cache.md"
            if cache.exists():
                targets.append(cache)

    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear dev-activity-report caches.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete files. Without this flag, runs as a dry-run.",
    )
    args = parser.parse_args()

    env = load_env()
    apps_dir = expand(env.get("APPS_DIR", APPS_DIR_DEFAULT))

    targets = collect_cache_files(apps_dir)

    if not targets:
        print("No cache files found — already clean.")
        return

    label = "Deleting" if args.confirm else "Would delete (dry-run)"
    for path in targets:
        print(f"  {label}: {path}")

    if args.confirm:
        for path in targets:
            path.unlink()
        print(f"\nRemoved {len(targets)} cache file(s). Next run will do a full fresh scan.")
    else:
        print(f"\nDry-run: {len(targets)} file(s) would be removed. Pass --confirm to delete.")


if __name__ == "__main__":
    main()
