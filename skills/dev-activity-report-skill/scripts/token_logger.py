#!/usr/bin/env python3
"""Utility to append token usage records and a brief build summary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from dotenv import dotenv_values  # type: ignore
except ImportError:  # pragma: no cover - fallback when python-dotenv is absent
    dotenv_values = None


def load_env(skill_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = skill_dir / ".env"
    if dotenv_values and env_path.exists():
        env.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    else:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def expand_path(value: str) -> Path:
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(value))))


def append_usage(
    skill_dir: Path,
    phase: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    price_in: Optional[float] = None,
    price_out: Optional[float] = None,
    log_path: Optional[Path] = None,
    build_log_path: Optional[Path] = None,
) -> float:
    """Append a JSONL record and return computed cost."""

    env = load_env(skill_dir)
    report_dir = expand_path(env.get("REPORT_OUTPUT_DIR", "~"))
    token_log = expand_path(env.get("TOKEN_LOG_PATH", str(report_dir / "token_economics.log")))
    build_log = expand_path(env.get("BUILD_LOG_PATH", str(report_dir / "build.log")))
    if log_path:
        token_log = log_path
    if build_log_path:
        build_log = build_log_path

    if price_in is None:
        raw_in = env.get("PRICE_PHASE2_IN")
        if raw_in:
            price_in = float(raw_in)
        else:
            print(f"warning: no price_in provided for phase={phase}; cost will be 0", file=sys.stderr)
            price_in = 0.0
    if price_out is None:
        raw_out = env.get("PRICE_PHASE2_OUT")
        if raw_out:
            price_out = float(raw_out)
        else:
            print(f"warning: no price_out provided for phase={phase}; cost will be 0", file=sys.stderr)
            price_out = 0.0

    total_tokens = prompt_tokens + completion_tokens
    cost = (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost": round(cost, 6),
    }
    token_log.parent.mkdir(parents=True, exist_ok=True)
    with token_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    build_log.parent.mkdir(parents=True, exist_ok=True)
    with build_log.open("a", encoding="utf-8") as fh:
        fh.write(
            f"Token usage: {total_tokens} tokens, Cost: ${record['cost']:.4f} "
            f"(phase={phase}, model={model}, ts={record['ts']})\n"
        )
    return cost


def main() -> None:
    parser = argparse.ArgumentParser(description="Append token economics entry.")
    parser.add_argument("--phase", required=True, help="phase label, e.g., 1.5 or 2")
    parser.add_argument("--model", required=True, help="model name")
    parser.add_argument("--prompt-tokens", type=int, required=True)
    parser.add_argument("--completion-tokens", type=int, required=True)
    parser.add_argument("--price-in", type=float, default=None, help="input price per 1M tokens")
    parser.add_argument("--price-out", type=float, default=None, help="output price per 1M tokens")
    parser.add_argument("--log-path", type=Path, default=None, help="override token log path")
    parser.add_argument("--build-log-path", type=Path, default=None, help="override build log path")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parent.parent
    append_usage(
        skill_dir=skill_dir,
        phase=str(args.phase),
        model=args.model,
        prompt_tokens=args.prompt_tokens,
        completion_tokens=args.completion_tokens,
        price_in=args.price_in,
        price_out=args.price_out,
        log_path=args.log_path,
        build_log_path=args.build_log_path,
    )


if __name__ == "__main__":
    main()
