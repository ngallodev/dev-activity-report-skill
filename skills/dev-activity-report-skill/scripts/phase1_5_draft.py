#!/usr/bin/env python3
"""Phase 1.5 draft synthesis — cheap model creates a rough outline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from dotenv import dotenv_values  # type: ignore
except ImportError:  # pragma: no cover
    dotenv_values = None

try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore

# Local import (minimal, no heavy deps)
sys.path.append(str(Path(__file__).resolve().parent))
try:
    from token_logger import append_usage
except Exception:  # pragma: no cover
    append_usage = None  # type: ignore

SKILL_DIR = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    env_path = SKILL_DIR / ".env"
    env: dict[str, str] = {}
    if dotenv_values and env_path.exists():
        env.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    elif env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def build_prompt(summary: Dict[str, Any]) -> str:
    return (
        "You are a terse assistant drafting a dev activity report. "
        "Input JSON uses abbreviated keys (see PAYLOAD_REFERENCE). "
        "Write a bullet draft only; no commentary.\n\n"
        f"Summary:\n{json.dumps(summary, separators=(',',':'))}\n\n"
        "Output:\n- 5–8 bullets (concise)\n- 2 sentence overview"
    )


def call_model(prompt: str, env: dict[str, str], summary: Dict[str, Any]) -> tuple[str, dict[str, int]]:
    model = env.get("PHASE15_MODEL") or "haiku"
    base = env.get("PHASE15_API_BASE") or env.get("OPENAI_API_BASE")
    api_key = env.get("PHASE15_API_KEY") or env.get("OPENAI_API_KEY")

    if OpenAI and api_key:
        client = OpenAI(api_key=api_key, base_url=base) if base else OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": "Draft concise dev activity bullets."},
                      {"role": "user", "content": prompt}],
            temperature=0.2,
        )
        usage = resp.usage or {}
        text = resp.choices[0].message.content.strip()
        return text, {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }

    # Fallback: deterministic heuristic draft if no API credentials.
    lines = []
    for proj in summary.get("p", [])[:6]:
        name = proj.get("n", "project")
        cc = proj.get("cc", 0)
        hl = ", ".join(proj.get("hl", [])[:2]) or "updates"
        lines.append(f"- {name}: {cc} commits; themes: {hl}")
    overview = "Overview: refreshed projects based on compact payload; API fallback used."
    text = "\n".join(lines + [overview])
    return text, {"prompt_tokens": 0, "completion_tokens": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Phase 1.5 draft from Phase 1 JSON.")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to Phase 1 JSON output. If omitted, read from stdin.",
    )
    args = parser.parse_args()

    raw = args.input.read_text() if args.input else sys.stdin.read()
    wrapped = json.loads(raw)
    summary = wrapped.get("data") or wrapped

    env = load_env()
    prompt = build_prompt(summary)
    draft, usage = call_model(prompt, env, summary)

    record_cost = None
    if append_usage:
        try:
            record_cost = append_usage(
                skill_dir=SKILL_DIR,
                phase="1.5",
                model=env.get("PHASE15_MODEL", "haiku"),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                price_in=float(env.get("PRICE_PHASE15_IN", 0) or 0),
                price_out=float(env.get("PRICE_PHASE15_OUT", 0) or 0),
            )
        except Exception:
            pass

    output = {
        "draft": draft,
        "usage": usage,
        "cost": record_cost,
    }
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
