#!/usr/bin/env python3
"""One-command installer and .env setup helper for dev-activity-report."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
EXAMPLE_NAME = ".env.example"
DEFAULT_INSTALL_DIR = Path.home() / ".claude" / "skills" / "dev-activity-report"

PROMPT_KEYS = {
    "APPS_DIR",
    "EXTRA_SCAN_DIRS",
    "CODEX_HOME",
    "CLAUDE_HOME",
    "PHASE1_MODEL",
    "PHASE15_MODEL",
    "PHASE2_MODEL",
    "PHASE3_MODEL",
    "REPORT_OUTPUT_DIR",
    "REPORT_FILENAME_PREFIX",
    "RESUME_HEADER",
}
AUTO_FILL_KEYS = {
    "CODEX_HOME",
    "CLAUDE_HOME",
    "APPS_DIR",
    "REPORT_OUTPUT_DIR",
    "REPORT_FILENAME_PREFIX",
    "RESUME_HEADER",
}

SYNC_SKIP_FILES = {
    ".env",
    ".phase1-cache.json",
    ".phase1-cache.tmp",
    ".dev-report-cache.md",
}
SYNC_SKIP_SUFFIXES = (".pyc", ".log")
SYNC_SKIP_DIRS = {"__pycache__"}


class InstallError(RuntimeError):
    """Raised when installer preconditions are not satisfied."""


def prompt(value: str, label: str) -> str:
    raw = input(f"{label} [{value}]: ").strip()
    return raw or value


def auto_fill(key: str, value: str) -> str:
    if key in AUTO_FILL_KEYS:
        return os.environ.get(key, value)
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def same_file(src: Path, dst: Path) -> bool:
    return dst.exists() and src.stat().st_size == dst.stat().st_size and file_sha256(src) == file_sha256(dst)


def should_skip(relative_path: Path) -> bool:
    if any(part in SYNC_SKIP_DIRS for part in relative_path.parts):
        return True
    name = relative_path.name
    if name in SYNC_SKIP_FILES:
        return True
    return name.endswith(SYNC_SKIP_SUFFIXES)


def verify_python_runtime() -> None:
    if sys.version_info < (3, 9):
        raise InstallError(f"Python 3.9+ is required (found {sys.version.split()[0]}).")


def verify_claude_cli() -> None:
    claude_path = shutil.which("claude")
    if not claude_path:
        raise InstallError("Claude CLI not found on PATH. Install/authenticate Claude Code first.")
    try:
        subprocess.run(
            ["claude", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError(f"Claude CLI is not runnable ({exc}).") from exc


def verify_prerequisites() -> None:
    errors = []
    try:
        verify_python_runtime()
    except InstallError as exc:
        errors.append(str(exc))
    try:
        verify_claude_cli()
    except InstallError as exc:
        errors.append(str(exc))
    if errors:
        raise InstallError("\n".join(errors))


def sync_skill(install_dir: Path, *, dry_run: bool) -> dict[str, int]:
    stats = {"created": 0, "updated": 0, "unchanged": 0, "dirs_created": 0}
    if not dry_run:
        install_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(SKILL_DIR.rglob("*")):
        rel = source.relative_to(SKILL_DIR)
        if should_skip(rel):
            continue
        target = install_dir / rel
        if source.is_dir():
            if not target.exists():
                stats["dirs_created"] += 1
                if not dry_run:
                    target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists() and same_file(source, target):
            stats["unchanged"] += 1
            continue
        if target.exists():
            stats["updated"] += 1
        else:
            stats["created"] += 1
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
        if not dry_run:
            shutil.copy2(source, target)
    return stats


def configure_env(skill_dir: Path, *, non_interactive: bool, dry_run: bool) -> str:
    env_template = skill_dir / "references" / "examples" / EXAMPLE_NAME
    env_file = skill_dir / ".env"
    if not env_template.exists():
        if dry_run:
            return f"Would initialize {env_file} from template after sync."
        raise InstallError(f"Missing template: {env_template}")

    if not env_file.exists():
        if dry_run:
            return f"Would create {env_file} from template."
        shutil.copy(env_template, env_file)

    lines = env_file.read_text().splitlines()
    out = []
    changed = False
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key, value = line.split("=", 1)
        value = auto_fill(key, value)
        if not non_interactive and key in PROMPT_KEYS:
            value = prompt(value, key)
        new_line = f"{key}={value}"
        changed = changed or (new_line != line)
        out.append(new_line)
    rendered = "\n".join(out) + "\n"
    if dry_run:
        return f"Would update {env_file}." if changed else f"No .env changes needed at {env_file}."
    if env_file.read_text() != rendered:
        env_file.write_text(rendered)
        return f"Updated {env_file}."
    return f"No .env changes needed at {env_file}."


def run_installer(args: argparse.Namespace) -> None:
    verify_prerequisites()
    install_dir = args.install_dir.expanduser().resolve()
    sync_stats = sync_skill(install_dir, dry_run=args.dry_run)
    print(f"Skill source:  {SKILL_DIR}")
    print(f"Skill target:  {install_dir}")
    print(
        "Sync result:   "
        f"{sync_stats['created']} created, "
        f"{sync_stats['updated']} updated, "
        f"{sync_stats['unchanged']} unchanged"
        + (" (dry-run)" if args.dry_run else "")
    )
    if not args.skip_setup:
        print(configure_env(install_dir, non_interactive=args.non_interactive, dry_run=args.dry_run))
    print("Installer completed safely; no files were deleted.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install/sync dev-activity-report into ~/.claude/skills.")
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=DEFAULT_INSTALL_DIR,
        help=f"Install location (default: {DEFAULT_INSTALL_DIR})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview sync/setup actions without writing files.")
    parser.add_argument("--skip-setup", action="store_true", help="Skip .env setup in the installed skill.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for key .env values (default is non-interactive/autofill).",
    )
    parser.add_argument(
        "--configure-only",
        action="store_true",
        help="Run .env setup for the current repo copy only (legacy behavior).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.non_interactive = not args.interactive
    try:
        if args.configure_only:
            verify_python_runtime()
            print(configure_env(SKILL_DIR, non_interactive=args.non_interactive, dry_run=args.dry_run))
            print("Setup completed safely; no files were deleted.")
            return
        run_installer(args)
    except InstallError as exc:
        raise SystemExit(f"Installer failed:\n{exc}") from exc


if __name__ == "__main__":
    main()
