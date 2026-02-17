#!/usr/bin/env python3
"""
Consolidate dev-activity-report outputs and codex test reports into a single
deduplicated document grouped by normalized headings.

Uncategorized headings are collected into an "Other" bucket rather than
silently dropped, so no content is lost.
"""
from __future__ import annotations

import argparse
import os
import re
import tarfile
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# Canonical section order in the output document
SECTION_ORDER = [
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
    "Other",
]


def normalize_heading(title: str) -> str:
    """Map an arbitrary heading title to a canonical section name.

    Unknown headings return "Other" so no content is silently discarded.
    """
    t = title.lower()
    if "resume bullet" in t:
        return "Resume Bullets"
    if "linkedin summary" in t:
        return "LinkedIn Summary"
    if "most resume-worthy" in t:
        return "Most Resume-Worthy Items"
    # "hiring manager" (space) OR "hiring-manager" (hyphen)
    if "hiring" in t and ("manager" in t or "highlight" in t):
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
    # "tech inventory", "technology inventory", "short tech inventory"
    if "tech inventory" in t or "technology inventory" in t:
        return "Tech Inventory"
    # "timeline", "5-row timeline", "timeline (most recent first)", etc.
    if "timeline" in t:
        return "Timeline"
    return "Other"


def extract_entries(lines: list[str]) -> list[str]:
    """Parse body lines into discrete entries (bullets, paragraphs, table rows)."""
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
        stripped = line.strip()
        if not stripped:
            flush_para()
            continue
        if stripped == "---":
            flush_para()
            continue
        if line.lstrip().startswith("|"):
            flush_para()
            entries.append(line.rstrip())
            continue
        if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            flush_para()
            entries.append(stripped)
            continue
        if re.match(r"^\s*\*\*.*\*\*\s*$", line):
            flush_para()
            entries.append(stripped)
            continue
        para.append(line)
    flush_para()
    return entries


def _detect_table_header(entries: list[str]) -> list[str] | None:
    """Return the first two table rows (header + separator) if present."""
    table_lines = [e for e in entries if e.startswith("|")]
    if len(table_lines) >= 2:
        return table_lines[:2]
    return None


def build_sections(
    report_paths: list[Path],
) -> tuple[OrderedDict[str, OrderedDict[str, None]], dict[str, list[str] | None]]:
    sections: OrderedDict[str, OrderedDict[str, None]] = OrderedDict(
        (name, OrderedDict()) for name in SECTION_ORDER
    )
    # Store one table header row-pair per section (first encountered wins)
    table_headers: dict[str, list[str] | None] = {name: None for name in SECTION_ORDER}

    def add_entry(section: str, entry: str) -> None:
        sections[section][entry] = None

    def flush_section(norm: str, body_lines: list[str]) -> None:
        if not norm:
            return
        entries = extract_entries(body_lines)
        if table_headers[norm] is None:
            header = _detect_table_header(entries)
            if header:
                table_headers[norm] = header
        for entry in entries:
            add_entry(norm, entry)

    for path in report_paths:
        text = path.read_text()
        lines = text.splitlines()

        # First pass: collect Findings sub-headings (children of Findings section)
        stack: list[dict[str, object]] = []
        for line in lines:
            m = HEADING_RE.match(line)
            if not m:
                continue
            level = len(m.group(1))
            title = m.group(2).strip()
            norm = normalize_heading(title)
            while stack and stack[-1]["level"] >= level:  # type: ignore[operator]
                stack.pop()
            parent_norm = stack[-1]["norm"] if stack else None
            stack.append({"level": level, "title": title, "norm": norm})
            # Sub-headings inside Findings become bold labels in that section
            if norm == "Other" and parent_norm == "Findings":
                add_entry("Findings", f"**{title}**")

        # Second pass: parse section bodies
        current_norm: str = ""
        current_lines: list[str] = []
        for line in lines:
            m = HEADING_RE.match(line)
            if m:
                flush_section(current_norm, current_lines)
                title = m.group(2).strip()
                current_norm = normalize_heading(title)
                current_lines = []
            elif current_norm:
                current_lines.append(line)
        flush_section(current_norm, current_lines)

    # Remove table separator rows and duplicate header rows from entries
    for sec_name in sections:
        header_set = set(table_headers.get(sec_name) or [])
        cleaned: OrderedDict[str, None] = OrderedDict()
        for entry in sections[sec_name]:
            if entry.strip() == "---":
                continue
            if entry.startswith("|"):
                if entry in header_set:
                    continue
                # Pure separator row like |---|---|
                if re.match(r"^\|\s*[-: |]+\s*\|?\s*$", entry):
                    continue
            cleaned[entry] = None
        sections[sec_name] = cleaned

    return sections, table_headers


def write_output(
    output_path: Path,
    sections: OrderedDict[str, OrderedDict[str, None]],
    table_headers: dict[str, list[str] | None],
    title: str,
    source_count: int,
) -> None:
    with output_path.open("w") as f:
        f.write(f"# {title}\n\n")
        f.write(
            f"Consolidated from {source_count} report(s). "
            "Unique entries deduplicated and grouped by section.\n\n"
        )
        for sec_name, entries in sections.items():
            if not entries:
                continue
            f.write(f"## {sec_name}\n\n")
            header = table_headers.get(sec_name)
            has_table = any(e.startswith("|") for e in entries)
            if has_table and header:
                f.write(header[0] + "\n")
                f.write(header[1] + "\n")
            for entry in entries:
                if entry.startswith("|"):
                    f.write(f"{entry}\n")
                elif re.match(r"^\s*[-*+]\s+", entry) or re.match(r"^\s*\d+\.\s+", entry):
                    f.write(f"{entry}\n")
                elif entry.startswith("**") and entry.endswith("**"):
                    f.write(f"{entry}\n")
                else:
                    f.write(f"{entry}\n\n")
            f.write("\n")


def collect_report_paths(
    test_root: Path,
    report_root: Path,
    test_glob: str,
    report_glob: str,
    output_path: Path,
) -> list[Path]:
    paths: list[Path] = []
    if test_root.exists():
        paths.extend(sorted(test_root.glob(test_glob)))
    if report_root.exists():
        paths.extend(sorted(report_root.glob(report_glob)))
    # Exclude the output file itself if it happens to match a glob
    resolved_output = output_path.resolve()
    return [p for p in dict.fromkeys(paths) if p.resolve() != resolved_output]


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate dev-activity-report outputs.")
    parser.add_argument(
        "--test-report-root",
        default=os.environ.get("DAR_TEST_REPORT_ROOT", ""),
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
    output_path = Path(os.path.expanduser(args.output))
    test_root = Path(os.path.expanduser(args.test_report_root)) if args.test_report_root else Path("/nonexistent")
    report_root = Path(os.path.expanduser(args.report_root))

    t0 = time.monotonic()
    report_paths = collect_report_paths(
        test_root, report_root, args.test_report_glob, args.report_glob, output_path
    )

    if not report_paths:
        raise SystemExit("No reports found to consolidate.")

    sections, table_headers = build_sections(report_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_output(output_path, sections, table_headers, args.title, len(report_paths))
    elapsed = time.monotonic() - t0

    total_entries = sum(len(v) for v in sections.values())
    nonempty = sum(1 for v in sections.values() if v)
    print(output_path)
    print(
        f"  {len(report_paths)} reports · {nonempty} sections · {total_entries} entries · {elapsed:.2f}s",
        flush=True,
    )

    # Archive source reports into a timestamped tar.gz alongside the output file
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = output_path.stem  # e.g. "dev-activity-report-aggregate"
    archive_path = output_path.parent / f"{stem}-consolidated-{ts}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for p in report_paths:
            tar.add(p, arcname=p.name)
    print(f"  archived → {archive_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
