#!/usr/bin/env python3
"""
Consolidate dev-activity-report outputs and codex test reports into a single
deduplicated document grouped by normalized headings.
"""
from __future__ import annotations

import argparse
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Iterable


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def normalize_heading(title: str) -> str | None:
    t = title.lower()
    if "resume bullet" in t:
        return "Resume Bullets"
    if "linkedin summary" in t:
        return "LinkedIn Summary"
    if "most resume-worthy" in t:
        return "Most Resume-Worthy Items"
    if "hiring manager highlight" in t:
        return "Hiring Manager Highlights"
    if "scan summary" in t:
        return "Scan Summary"
    if "original work project" in t:
        return "Original Work Projects"
    if "forked" in t:
        return "Forked & Modified Projects"
    if "technical problem" in t:
        return "Technical Problems Solved"
    if "ai-assisted development" in t:
        return "AI-Assisted Development Workflows"
    if "codex activity" in t:
        return "Codex Activity"
    if "ai workflow pattern" in t:
        return "AI Workflow Patterns"
    if t.strip() == "findings" or t.startswith("findings"):
        return "Findings"
    if "tech inventory" in t or "technology inventory" in t:
        return "Tech Inventory"
    if "timeline" in t:
        return "Timeline"
    return None


def extract_entries(lines: Iterable[str]) -> list[str]:
    entries: list[str] = []
    para: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if para:
            text = " ".join(p.strip() for p in para).strip()
            if text and text != "---":
                entries.append(text)
            para = []

    for line in lines:
        if not line.strip():
            flush_para()
            continue
        if line.strip() == "---":
            flush_para()
            continue
        if line.lstrip().startswith("|"):
            flush_para()
            entries.append(line.rstrip())
            continue
        if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            flush_para()
            entries.append(line.strip())
            continue
        if re.match(r"^\s*\*\*.*\*\*\s*$", line):
            flush_para()
            entries.append(line.strip())
            continue
        para.append(line)
    flush_para()
    return entries


def iter_reports(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for p in paths:
        if p.is_file():
            found.append(p)
        elif p.is_dir():
            for child in p.glob("*.md"):
                found.append(child)
    return sorted(set(found))


def build_sections(report_paths: list[Path]) -> tuple[OrderedDict, dict[str, list[str] | None]]:
    section_order = [
        "Resume Bullets",
        "LinkedIn Summary",
        "Most Resume-Worthy Items",
        "Hiring Manager Highlights",
        "Scan Summary",
        "Original Work Projects",
        "Forked & Modified Projects",
        "Technical Problems Solved",
        "AI-Assisted Development Workflows",
        "Codex Activity",
        "AI Workflow Patterns",
        "Findings",
        "Tech Inventory",
        "Timeline",
    ]
    sections: OrderedDict[str, OrderedDict[str, None]] = OrderedDict(
        (name, OrderedDict()) for name in section_order
    )
    table_headers: dict[str, list[str] | None] = {name: None for name in section_order}

    def add_entry(section: str, entry: str) -> None:
        sections[section][entry] = None

    for path in report_paths:
        text = path.read_text()
        lines = text.splitlines()

        # Collect Findings subheadings
        stack: list[dict[str, object]] = []
        for line in lines:
            m = HEADING_RE.match(line)
            if not m:
                continue
            level = len(m.group(1))
            title = m.group(2).strip()
            norm = normalize_heading(title)
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            parent_norm = stack[-1]["norm"] if stack else None
            stack.append({"level": level, "title": title, "norm": norm})
            if norm is None and parent_norm == "Findings":
                add_entry("Findings", f"**{title}**")

        # Parse section bodies
        current_norm = None
        current_lines: list[str] = []
        for line in lines:
            m = HEADING_RE.match(line)
            if m:
                if current_norm:
                    entries = extract_entries(current_lines)
                    for entry in entries:
                        if entry.startswith("|") and table_headers[current_norm] is None:
                            table_lines = [e for e in entries if e.startswith("|")]
                            if len(table_lines) >= 2:
                                table_headers[current_norm] = table_lines[:2]
                        add_entry(current_norm, entry)
                title = m.group(2).strip()
                current_norm = normalize_heading(title)
                current_lines = []
                continue
            if current_norm:
                current_lines.append(line)
        if current_norm:
            entries = extract_entries(current_lines)
            for entry in entries:
                if entry.startswith("|") and table_headers[current_norm] is None:
                    table_lines = [e for e in entries if e.startswith("|")]
                    if len(table_lines) >= 2:
                        table_headers[current_norm] = table_lines[:2]
                add_entry(current_norm, entry)

    # Clean: remove headers/separators and keep only unique entries
    for sec_name in sections:
        cleaned: OrderedDict[str, None] = OrderedDict()
        header = table_headers.get(sec_name) or []
        header_set = set(header)
        for entry in sections[sec_name].keys():
            if entry.strip() == "---":
                continue
            if entry.startswith("|"):
                if entry in header_set:
                    continue
                if re.match(r"^\|\s*[-: ]+\|?$", entry.strip()):
                    continue
            cleaned[entry] = None
        sections[sec_name] = cleaned

    return sections, table_headers


def write_output(
    output_path: Path,
    sections: OrderedDict,
    table_headers: dict[str, list[str] | None],
    title: str,
) -> None:
    with output_path.open("w") as f:
        f.write(f"# {title}\n\n")
        f.write(
            "This document consolidates unique entries across all dev-activity-report outputs "
            "and codex test reports found in the workspace.\n\n"
        )
        for sec_name, entries in sections.items():
            if not entries:
                continue
            f.write(f"## {sec_name}\n\n")
            header = table_headers.get(sec_name)
            has_table = any(e.startswith("|") for e in entries.keys())
            if has_table and header:
                f.write(header[0] + "\n")
                f.write(header[1] + "\n")
            for entry in entries.keys():
                if entry.startswith("|"):
                    f.write(f"{entry}\n")
                    continue
                if re.match(r"^\s*[-*+]\s+", entry) or re.match(r"^\s*\d+\.\s+", entry):
                    f.write(f"{entry}\n")
                    continue
                if entry.startswith("**") and entry.endswith("**"):
                    f.write(f"{entry}\n")
                    continue
                f.write(f"{entry}\n\n")
            f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate dev-activity-report outputs.")
    parser.add_argument(
        "--test-report-root",
        default=os.environ.get("DAR_TEST_REPORT_ROOT", "/lump/apps/dev-activity-report-skill"),
        help="Directory containing codex-test-report-*.md files.",
    )
    parser.add_argument(
        "--report-root",
        default=os.environ.get("DAR_REPORT_ROOT", str(Path.home())),
        help="Directory containing dev-activity-report-*.md files.",
    )
    parser.add_argument(
        "--test-report-glob",
        default=os.environ.get("DAR_TEST_REPORT_GLOB", "codex-test-report-*.md"),
        help="Glob for codex test reports.",
    )
    parser.add_argument(
        "--report-glob",
        default=os.environ.get("DAR_REPORT_GLOB", "dev-activity-report-*.md"),
        help="Glob for dev-activity reports.",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get(
            "DAR_AGGREGATE_OUTPUT",
            str(Path.home() / "dev-activity-report-aggregate.md"),
        ),
        help="Output markdown path.",
    )
    parser.add_argument(
        "--title",
        default=os.environ.get("DAR_AGGREGATE_TITLE", "Dev Activity Report — Aggregate"),
        help="Document title.",
    )

    args = parser.parse_args()
    test_root = Path(os.path.expanduser(args.test_report_root))
    report_root = Path(os.path.expanduser(args.report_root))
    output_path = Path(os.path.expanduser(args.output))

    report_paths = []
    if test_root.exists():
        report_paths.extend(sorted(test_root.glob(args.test_report_glob)))
    if report_root.exists():
        report_paths.extend(sorted(report_root.glob(args.report_glob)))

    if not report_paths:
        raise SystemExit("No reports found to consolidate.")

    sections, table_headers = build_sections(report_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_output(output_path, sections, table_headers, args.title)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
