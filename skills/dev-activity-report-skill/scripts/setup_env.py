#!/usr/bin/env python3
"""Interactive .env setup helper for dev-activity-report-skill."""

from __future__ import annotations

import shutil
from pathlib import Path
import os

SKILL_DIR = Path(__file__).resolve().parent.parent
EXAMPLE = SKILL_DIR / "references" / "examples" / ".env.example"
ENV_FILE = SKILL_DIR / ".env"


def prompt(value: str, label: str) -> str:
    raw = input(f"{label} [{value}]: ").strip()
    return raw or value


def auto_fill(key: str, value: str) -> str:
    if key == "CODEX_HOME":
        return os.environ.get("CODEX_HOME", value)
    if key == "CLAUDE_HOME":
        return os.environ.get("CLAUDE_HOME", value)
    if key == "APPS_DIR":
        return os.environ.get("APPS_DIR", value)
    if key == "REPORT_OUTPUT_DIR":
        return os.environ.get("REPORT_OUTPUT_DIR", value)
    if key == "REPORT_FILENAME_PREFIX":
        return os.environ.get("REPORT_FILENAME_PREFIX", value)
    if key == "RESUME_HEADER":
        return os.environ.get("RESUME_HEADER", value)
    return value


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Setup .env for dev-activity-report-skill.")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt; only autofill.")
    args = parser.parse_args()

    if not EXAMPLE.exists():
        raise SystemExit(f"Missing template: {EXAMPLE}")

    if not ENV_FILE.exists():
        shutil.copy(EXAMPLE, ENV_FILE)

    lines = ENV_FILE.read_text().splitlines()
    out = []
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key, value = line.split("=", 1)
        value = auto_fill(key, value)
        if args.non_interactive:
            out.append(f"{key}={value}")
            continue
        if key in {"APPS_DIR", "EXTRA_SCAN_DIRS", "CODEX_HOME", "CLAUDE_HOME"}:
            new_val = prompt(value, key)
            out.append(f"{key}={new_val}")
        elif key in {"PHASE1_MODEL", "PHASE15_MODEL", "PHASE2_MODEL", "PHASE3_MODEL"}:
            new_val = prompt(value, key)
            out.append(f"{key}={new_val}")
        elif key in {"REPORT_OUTPUT_DIR", "REPORT_FILENAME_PREFIX", "RESUME_HEADER"}:
            new_val = prompt(value, key)
            out.append(f"{key}={new_val}")
        else:
            out.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(out) + "\n")
    print(f"Wrote {ENV_FILE}")


if __name__ == "__main__":
    main()
