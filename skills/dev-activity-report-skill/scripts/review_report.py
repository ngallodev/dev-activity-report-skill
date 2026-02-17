#!/usr/bin/env python3
"""Minimal interactive editor for phase 2 report JSON before render."""

from __future__ import annotations

from copy import deepcopy
from typing import Callable


InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]


def _safe_input(input_fn: InputFn, prompt: str) -> str:
    try:
        return input_fn(prompt)
    except EOFError:
        return ""
    except KeyboardInterrupt:
        return "q"


def _parse_indexes(raw: str, size: int) -> list[int]:
    values: set[int] = set()
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= size:
                values.add(idx - 1)
            continue
        if "-" in token:
            parts = token.split("-", 1)
            if parts[0].strip().isdigit() and parts[1].strip().isdigit():
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                if start > end:
                    start, end = end, start
                for idx in range(start, end + 1):
                    if 1 <= idx <= size:
                        values.add(idx - 1)
    return sorted(values)


def _edit_text_list(
    title: str,
    items: list[str],
    input_fn: InputFn,
    output_fn: OutputFn,
) -> tuple[list[str], bool, bool]:
    changed = False
    while True:
        output_fn(f"\n[{title}]")
        if items:
            for idx, item in enumerate(items, start=1):
                output_fn(f"  {idx}. {item}")
        else:
            output_fn("  (empty)")
        output_fn("  cmd: Enter=next | d 1,3 prune | e 2 <text> edit | a <text> add | x clear | q quit")
        cmd = _safe_input(input_fn, "> ").strip()
        if not cmd:
            break
        if cmd == "q":
            return items, changed, True
        if cmd == "x":
            if items:
                items = []
                changed = True
            continue
        if cmd.startswith("d "):
            indexes = _parse_indexes(cmd[2:].strip(), len(items))
            if indexes:
                items = [v for i, v in enumerate(items) if i not in set(indexes)]
                changed = True
            continue
        if cmd.startswith("e "):
            parts = cmd.split(" ", 2)
            if len(parts) < 3 or not parts[1].isdigit():
                output_fn("  invalid edit command")
                continue
            pos = int(parts[1]) - 1
            if pos < 0 or pos >= len(items):
                output_fn("  out-of-range index")
                continue
            items[pos] = parts[2].strip()
            changed = True
            continue
        if cmd.startswith("a "):
            text = cmd[2:].strip()
            if text:
                items.append(text)
                changed = True
            continue
        output_fn("  unknown command")
    return items, changed, False


def _edit_key_changes(
    sections: dict,
    input_fn: InputFn,
    output_fn: OutputFn,
) -> tuple[dict, bool, bool]:
    changed = False
    quit_all = False
    key_changes = sections.get("key_changes")
    if not isinstance(key_changes, list):
        key_changes = []
    while True:
        output_fn("\n[Key Changes]")
        if key_changes:
            for idx, item in enumerate(key_changes, start=1):
                title = item.get("title", "(untitled)") if isinstance(item, dict) else "(invalid)"
                count = len(item.get("bullets", [])) if isinstance(item, dict) and isinstance(item.get("bullets"), list) else 0
                output_fn(f"  {idx}. {title} ({count} bullets)")
        else:
            output_fn("  (empty)")
        output_fn("  cmd: Enter=next | d 1 prune | t 1 <title> rename | b 1 edit bullets | g <title> add group | x clear | q quit")
        cmd = _safe_input(input_fn, "> ").strip()
        if not cmd:
            break
        if cmd == "q":
            quit_all = True
            break
        if cmd == "x":
            if key_changes:
                key_changes = []
                changed = True
            continue
        if cmd.startswith("d "):
            indexes = _parse_indexes(cmd[2:].strip(), len(key_changes))
            if indexes:
                key_changes = [v for i, v in enumerate(key_changes) if i not in set(indexes)]
                changed = True
            continue
        if cmd.startswith("g "):
            title = cmd[2:].strip()
            if title:
                key_changes.append({"title": title, "project_id": None, "bullets": [], "tags": []})
                changed = True
            continue
        if cmd.startswith("t "):
            parts = cmd.split(" ", 2)
            if len(parts) < 3 or not parts[1].isdigit():
                output_fn("  invalid rename command")
                continue
            pos = int(parts[1]) - 1
            if pos < 0 or pos >= len(key_changes) or not isinstance(key_changes[pos], dict):
                output_fn("  out-of-range index")
                continue
            key_changes[pos]["title"] = parts[2].strip()
            changed = True
            continue
        if cmd.startswith("b "):
            parts = cmd.split(" ", 1)
            idx_raw = parts[1].strip() if len(parts) > 1 else ""
            if not idx_raw.isdigit():
                output_fn("  invalid bullet editor command")
                continue
            pos = int(idx_raw) - 1
            if pos < 0 or pos >= len(key_changes) or not isinstance(key_changes[pos], dict):
                output_fn("  out-of-range index")
                continue
            bullets = key_changes[pos].get("bullets")
            if not isinstance(bullets, list):
                bullets = []
            bullets, did_change, quit_from_bullets = _edit_text_list(
                f"Key Changes #{pos + 1} bullets",
                [str(v) for v in bullets],
                input_fn,
                output_fn,
            )
            if did_change:
                key_changes[pos]["bullets"] = bullets
                changed = True
            if quit_from_bullets:
                quit_all = True
                break
            continue
        output_fn("  unknown command")
    sections["key_changes"] = key_changes
    return sections, changed, quit_all


def run_interactive_review(
    report_obj: dict,
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
) -> tuple[dict, bool]:
    """Review core sections and allow small edits without model calls."""
    updated = deepcopy(report_obj)
    sections = updated.get("sections")
    if not isinstance(sections, dict):
        sections = {}
        updated["sections"] = sections

    output_fn("Interactive review enabled. Edit JSON now; rendering runs after this step.")
    output_fn("Use short commands only. Press Enter repeatedly to accept all sections.")

    changed_any = False

    overview = sections.get("overview") or {}
    bullets = overview.get("bullets") if isinstance(overview, dict) else []
    bullets = [str(v) for v in bullets] if isinstance(bullets, list) else []
    bullets, changed, quit_all = _edit_text_list("Overview bullets", bullets, input_fn, output_fn)
    if changed:
        changed_any = True
    sections["overview"] = {"bullets": bullets}
    if quit_all:
        return updated, changed_any

    sections, changed, quit_all = _edit_key_changes(sections, input_fn, output_fn)
    if changed:
        changed_any = True
    if quit_all:
        return updated, changed_any

    recommendations = sections.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
    rec_lines = []
    for rec in recommendations:
        if not isinstance(rec, dict):
            continue
        priority = str(rec.get("priority", "low"))
        rec_lines.append(f"[{priority}] {str(rec.get('text', ''))}")
    rec_lines, changed, quit_all = _edit_text_list("Recommendations", rec_lines, input_fn, output_fn)
    if changed:
        changed_any = True
    normalized_recs = []
    for line in rec_lines:
        text = line.strip()
        priority = "low"
        if text.startswith("[") and "]" in text:
            prefix, remainder = text.split("]", 1)
            maybe = prefix[1:].strip().lower()
            if maybe in ("low", "medium", "high"):
                priority = maybe
                text = remainder.strip()
        normalized_recs.append({"text": text, "priority": priority, "evidence_project_ids": []})
    sections["recommendations"] = normalized_recs
    if quit_all:
        return updated, changed_any

    resume = sections.get("resume_bullets")
    resume_lines = []
    if isinstance(resume, list):
        resume_lines = [str(item.get("text", "")) for item in resume if isinstance(item, dict)]
    resume_lines, changed, quit_all = _edit_text_list("Resume bullets", resume_lines, input_fn, output_fn)
    if changed:
        changed_any = True
    sections["resume_bullets"] = [{"text": line, "evidence_project_ids": []} for line in resume_lines]
    if quit_all:
        return updated, changed_any

    linkedin = sections.get("linkedin") or {}
    linkedin_lines = linkedin.get("sentences") if isinstance(linkedin, dict) else []
    linkedin_lines = [str(v) for v in linkedin_lines] if isinstance(linkedin_lines, list) else []
    linkedin_lines, changed, quit_all = _edit_text_list("LinkedIn sentences", linkedin_lines, input_fn, output_fn)
    if changed:
        changed_any = True
    sections["linkedin"] = {"sentences": linkedin_lines}
    if quit_all:
        return updated, changed_any

    highlights = sections.get("highlights")
    highlight_lines = []
    if isinstance(highlights, list):
        for item in highlights:
            if isinstance(item, dict):
                title = str(item.get("title", "")).strip()
                rationale = str(item.get("rationale", "")).strip()
                highlight_lines.append(f"{title} | {rationale}" if rationale else title)
    highlight_lines, changed, quit_all = _edit_text_list(
        "Highlights (title | rationale)",
        highlight_lines,
        input_fn,
        output_fn,
    )
    if changed:
        changed_any = True
    normalized_highlights = []
    for line in highlight_lines:
        if "|" in line:
            title, rationale = line.split("|", 1)
            normalized_highlights.append(
                {"title": title.strip(), "rationale": rationale.strip(), "evidence_project_ids": []}
            )
        else:
            normalized_highlights.append({"title": line.strip(), "rationale": "", "evidence_project_ids": []})
    sections["highlights"] = normalized_highlights
    if quit_all:
        return updated, changed_any

    return updated, changed_any
