#!/usr/bin/env python3
"""
Consolidate dev-activity-report outputs into aggregate JSON/Markdown/HTML.

Default behavior:
- Prefer JSON source reports when available
- Fall back to Markdown source only when requested (or when no JSON exists)
- Emit aggregate JSON + Markdown + HTML by default
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from render_report import render_html, render_markdown


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def normalize_heading(title: str) -> str:
    t = title.lower().strip()
    if "resume bullet" in t:
        return "resume_bullets"
    if "linkedin" in t:
        return "linkedin"
    if "highlight" in t or "most resume-worthy" in t:
        return "highlights"
    if "timeline" in t:
        return "timeline"
    if "tech inventory" in t or "technology inventory" in t:
        return "tech_inventory"
    if "recommend" in t:
        return "recommendations"
    if "overview" in t:
        return "overview"
    return "key_changes"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strip_bullet(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^[-*+]\s+", "", text)
    text = re.sub(r"^\d+\.\s+", "", text)
    return text.strip()


def _append_unique(out: list[Any], seen: set[str], item: Any, key: str) -> None:
    if key in seen:
        return
    seen.add(key)
    out.append(item)


def merge_json_reports(report_paths: list[Path], title: str) -> dict[str, Any]:
    sections: dict[str, Any] = {
        "overview": {"bullets": []},
        "key_changes": [],
        "recommendations": [],
        "resume_bullets": [],
        "linkedin": {"sentences": []},
        "highlights": [],
        "timeline": [],
        "tech_inventory": {
            "languages": [],
            "frameworks": [],
            "ai_tools": [],
            "infra": [],
        },
    }
    insights: dict[str, Any] = {"source": {}, "sections": [], "quotes": []}

    seen_overview: set[str] = set()
    seen_key_changes: set[str] = set()
    seen_recs: set[str] = set()
    seen_resume: set[str] = set()
    seen_linkedin: set[str] = set()
    seen_highlights: set[str] = set()
    seen_timeline: set[str] = set()
    seen_tech: dict[str, set[str]] = {k: set() for k in sections["tech_inventory"].keys()}
    seen_insight_sections: set[str] = set()
    seen_quotes: set[str] = set()

    for path in report_paths:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        sec = obj.get("sections") or {}

        for bullet in _as_list((sec.get("overview") or {}).get("bullets")):
            if isinstance(bullet, str) and bullet.strip():
                _append_unique(sections["overview"]["bullets"], seen_overview, bullet.strip(), bullet.strip())

        for item in _as_list(sec.get("key_changes")):
            if not isinstance(item, dict):
                continue
            title_key = str(item.get("title", "")).strip()
            bullets = [str(b).strip() for b in _as_list(item.get("bullets")) if str(b).strip()]
            key = f"{title_key}|{'|'.join(bullets)}"
            _append_unique(
                sections["key_changes"],
                seen_key_changes,
                {
                    "title": title_key or "Change",
                    "project_id": item.get("project_id") or None,
                    "bullets": bullets,
                    "tags": [str(t).strip() for t in _as_list(item.get("tags")) if str(t).strip()],
                },
                key,
            )

        for item in _as_list(sec.get("recommendations")):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            prio = str(item.get("priority", "")).strip().lower() or "low"
            key = f"{text}|{prio}"
            _append_unique(
                sections["recommendations"],
                seen_recs,
                {
                    "text": text,
                    "priority": prio if prio in {"low", "medium", "high"} else "low",
                    "evidence_project_ids": [str(e).strip() for e in _as_list(item.get("evidence_project_ids")) if str(e).strip()],
                },
                key,
            )

        for item in _as_list(sec.get("resume_bullets")):
            text = str(item.get("text", "")).strip() if isinstance(item, dict) else str(item).strip()
            if not text:
                continue
            _append_unique(
                sections["resume_bullets"],
                seen_resume,
                {"text": text, "evidence_project_ids": [] if not isinstance(item, dict) else [str(e).strip() for e in _as_list(item.get("evidence_project_ids")) if str(e).strip()]},
                text,
            )

        for sentence in _as_list((sec.get("linkedin") or {}).get("sentences")):
            if isinstance(sentence, str) and sentence.strip():
                _append_unique(sections["linkedin"]["sentences"], seen_linkedin, sentence.strip(), sentence.strip())

        for item in _as_list(sec.get("highlights")):
            if not isinstance(item, dict):
                continue
            title_val = str(item.get("title", "")).strip()
            rationale = str(item.get("rationale", "")).strip()
            if not title_val:
                continue
            key = f"{title_val}|{rationale}"
            _append_unique(
                sections["highlights"],
                seen_highlights,
                {
                    "title": title_val,
                    "rationale": rationale,
                    "evidence_project_ids": [str(e).strip() for e in _as_list(item.get("evidence_project_ids")) if str(e).strip()],
                },
                key,
            )

        for item in _as_list(sec.get("timeline")):
            if not isinstance(item, dict):
                continue
            date = str(item.get("date", "")).strip()
            event = str(item.get("event", "")).strip()
            if not (date or event):
                continue
            key = f"{date}|{event}"
            _append_unique(
                sections["timeline"],
                seen_timeline,
                {"date": date, "event": event, "project_ids": [str(p).strip() for p in _as_list(item.get("project_ids")) if str(p).strip()]},
                key,
            )

        tech = sec.get("tech_inventory") or {}
        for k in ("languages", "frameworks", "ai_tools", "infra"):
            for entry in _as_list(tech.get(k)):
                s = str(entry).strip()
                if not s or s in seen_tech[k]:
                    continue
                seen_tech[k].add(s)
                sections["tech_inventory"][k].append(s)

        ins = obj.get("insights") or {}
        if not insights["source"] and isinstance(ins.get("source"), dict):
            insights["source"] = ins.get("source")

        for sec_item in _as_list(ins.get("sections")):
            if not isinstance(sec_item, dict):
                continue
            sid = str(sec_item.get("section_id", "")).strip()
            title_val = str(sec_item.get("title", "")).strip()
            content = [str(c).strip() for c in _as_list(sec_item.get("content")) if str(c).strip()]
            key = sid or title_val
            if not key:
                continue
            if key not in seen_insight_sections:
                seen_insight_sections.add(key)
                insights["sections"].append(
                    {
                        "section_id": sid,
                        "title": title_val or "Insights",
                        "link": sec_item.get("link", ""),
                        "content": content,
                    }
                )
                continue
            for existing in insights["sections"]:
                if (existing.get("section_id") or existing.get("title")) == key:
                    existing_content = existing.get("content") or []
                    for line in content:
                        if line and line not in existing_content:
                            existing_content.append(line)
                    existing["content"] = existing_content
                    break

        for q in _as_list(ins.get("quotes")):
            if not isinstance(q, dict):
                continue
            quote = str(q.get("quote", "")).strip()
            if not quote or quote in seen_quotes:
                continue
            seen_quotes.add(quote)
            insights["quotes"].append(
                {
                    "quote": quote,
                    "source_path": q.get("source_path", ""),
                    "source_link": q.get("source_link", ""),
                    "section_id": q.get("section_id", ""),
                    "section_title": q.get("section_title", ""),
                }
            )

    return {
        "schema_version": "dev-activity-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "resume_header": title,
        "run": {"consolidated_reports": len(report_paths)},
        "source_summary": {"reports_consolidated": len(report_paths)},
        "sections": sections,
        "insights": insights,
        "render_hints": {"preferred_outputs": ["md", "html"], "style": "concise", "tone": "professional"},
        "source_payload": None,
    }


def _md_section_entries(lines: list[str]) -> list[str]:
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
        if not stripped or stripped == "---":
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
        para.append(line)
    flush_para()
    return entries


def merge_md_reports(report_paths: list[Path], title: str) -> dict[str, Any]:
    report = {
        "schema_version": "dev-activity-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "resume_header": title,
        "run": {"consolidated_reports": len(report_paths)},
        "source_summary": {"reports_consolidated": len(report_paths)},
        "sections": {
            "overview": {"bullets": []},
            "key_changes": [],
            "recommendations": [],
            "resume_bullets": [],
            "linkedin": {"sentences": []},
            "highlights": [],
            "timeline": [],
            "tech_inventory": {"languages": [], "frameworks": [], "ai_tools": [], "infra": []},
        },
        "insights": {"source": {}, "sections": [], "quotes": []},
        "render_hints": {"preferred_outputs": ["md", "html"], "style": "concise", "tone": "professional"},
        "source_payload": None,
    }

    seen: dict[str, set[str]] = {
        "overview": set(),
        "key_changes": set(),
        "recommendations": set(),
        "resume": set(),
        "linkedin": set(),
        "highlights": set(),
        "timeline": set(),
    }

    for path in report_paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        current_norm = ""
        current_lines: list[str] = []

        def flush_section(norm: str, body_lines: list[str]) -> None:
            if not norm:
                return
            entries = _md_section_entries(body_lines)
            if not entries:
                return
            if norm == "resume_bullets":
                for e in entries:
                    text = _strip_bullet(e)
                    if text and text not in seen["resume"]:
                        seen["resume"].add(text)
                        report["sections"]["resume_bullets"].append({"text": text, "evidence_project_ids": []})
            elif norm == "linkedin":
                for e in entries:
                    text = _strip_bullet(e)
                    if text and text not in seen["linkedin"]:
                        seen["linkedin"].add(text)
                        report["sections"]["linkedin"]["sentences"].append(text)
            elif norm == "highlights":
                for e in entries:
                    text = _strip_bullet(e)
                    if text and text not in seen["highlights"]:
                        seen["highlights"].add(text)
                        report["sections"]["highlights"].append({"title": text, "rationale": "", "evidence_project_ids": []})
            elif norm == "timeline":
                for e in entries:
                    if e.startswith("|") and not re.match(r"^\|\s*[:\- ]+\|", e):
                        cells = [c.strip() for c in e.strip("|").split("|")]
                        if len(cells) >= 2 and cells[0].lower() != "date":
                            key = f"{cells[0]}|{cells[1]}"
                            if key not in seen["timeline"]:
                                seen["timeline"].add(key)
                                report["sections"]["timeline"].append({"date": cells[0], "event": cells[1], "project_ids": []})
            elif norm == "recommendations":
                for e in entries:
                    text = _strip_bullet(e)
                    if text and text not in seen["recommendations"]:
                        seen["recommendations"].add(text)
                        report["sections"]["recommendations"].append({"text": text, "priority": "low", "evidence_project_ids": []})
            elif norm == "overview":
                for e in entries:
                    text = _strip_bullet(e)
                    if text and text not in seen["overview"]:
                        seen["overview"].add(text)
                        report["sections"]["overview"]["bullets"].append(text)
            else:
                title_val = path.name
                bullets = [
                    _strip_bullet(e)
                    for e in entries
                    if _strip_bullet(e) and _strip_bullet(e) not in seen["key_changes"]
                ]
                for b in bullets:
                    seen["key_changes"].add(b)
                if bullets:
                    report["sections"]["key_changes"].append(
                        {"title": title_val, "project_id": None, "bullets": bullets, "tags": ["legacy-md"]}
                    )

        for line in lines:
            m = HEADING_RE.match(line)
            if m:
                flush_section(current_norm, current_lines)
                current_norm = normalize_heading(m.group(2).strip())
                current_lines = []
            elif current_norm:
                current_lines.append(line)

        flush_section(current_norm, current_lines)

    return report


def collect_report_paths(
    test_root: Path,
    report_root: Path,
    test_glob: str,
    report_glob: str,
    output_base: Path,
) -> list[Path]:
    paths: list[Path] = []
    if test_root.exists():
        paths.extend(sorted(test_root.glob(test_glob)))
    if report_root.exists():
        paths.extend(sorted(report_root.glob(report_glob)))

    excluded = {
        output_base.resolve(),
        output_base.with_suffix(".md").resolve(),
        output_base.with_suffix(".html").resolve(),
        output_base.with_suffix(".json").resolve(),
    }
    return [p for p in dict.fromkeys(paths) if p.resolve() not in excluded]


def write_outputs(report_obj: dict[str, Any], output_base: Path, formats: list[str]) -> list[Path]:
    written: list[Path] = []
    output_base.parent.mkdir(parents=True, exist_ok=True)

    if "json" in formats:
        p = output_base.with_suffix(".json")
        p.write_text(json.dumps(report_obj, separators=(",", ":")), encoding="utf-8")
        written.append(p)
    if "md" in formats:
        p = output_base.with_suffix(".md")
        p.write_text(render_markdown(report_obj), encoding="utf-8")
        written.append(p)
    if "html" in formats:
        p = output_base.with_suffix(".html")
        p.write_text(render_html(report_obj), encoding="utf-8")
        written.append(p)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate dev-activity-report outputs.")
    parser.add_argument("--test-report-root", default=os.environ.get("DAR_TEST_REPORT_ROOT", ""))
    parser.add_argument("--report-root", default=os.environ.get("DAR_REPORT_ROOT", str(Path.home())))

    parser.add_argument("--test-report-glob", default=os.environ.get("DAR_TEST_REPORT_GLOB", "codex-test-report-*.md"))
    parser.add_argument("--report-glob", default=os.environ.get("DAR_REPORT_GLOB", "dev-activity-report-*.md"))
    parser.add_argument("--test-report-json-glob", default=os.environ.get("DAR_TEST_REPORT_JSON_GLOB", "codex-test-report-*.json"))
    parser.add_argument("--report-json-glob", default=os.environ.get("DAR_REPORT_JSON_GLOB", "dev-activity-report-*.json"))

    parser.add_argument(
        "--source-format",
        choices=("auto", "json", "md"),
        default=os.environ.get("DAR_SOURCE_FORMAT", "auto"),
        help="Source mode: auto prefers JSON if present; md forces markdown parsing.",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("DAR_AGGREGATE_OUTPUT", str(Path.home() / "dev-activity-report-aggregate.md")),
        help="Aggregate output path (base stem is used for json/md/html outputs).",
    )
    parser.add_argument(
        "--formats",
        default=os.environ.get("DAR_AGGREGATE_FORMATS", "json,md,html"),
        help="Comma-separated output formats: json,md,html",
    )
    parser.add_argument(
        "--title",
        default=os.environ.get("DAR_AGGREGATE_TITLE", "Dev Activity Report — Aggregate"),
    )

    args = parser.parse_args()

    output_path = Path(os.path.expanduser(args.output))
    output_base = output_path.with_suffix("") if output_path.suffix else output_path
    test_root = Path(os.path.expanduser(args.test_report_root)) if args.test_report_root else Path("/nonexistent")
    report_root = Path(os.path.expanduser(args.report_root))
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    for f in formats:
        if f not in {"json", "md", "html"}:
            raise SystemExit(f"Unsupported format: {f}")

    t0 = time.monotonic()

    json_paths = collect_report_paths(test_root, report_root, args.test_report_json_glob, args.report_json_glob, output_base)
    md_paths = collect_report_paths(test_root, report_root, args.test_report_glob, args.report_glob, output_base)

    source_mode = args.source_format
    selected_paths: list[Path]
    if source_mode == "json":
        selected_paths = json_paths
    elif source_mode == "md":
        selected_paths = md_paths
    else:
        if json_paths:
            source_mode = "json"
            selected_paths = json_paths
        else:
            source_mode = "md"
            selected_paths = md_paths

    if not selected_paths:
        raise SystemExit("No reports found to consolidate.")

    report_obj = (
        merge_json_reports(selected_paths, args.title)
        if source_mode == "json"
        else merge_md_reports(selected_paths, args.title)
    )

    written = write_outputs(report_obj, output_base, formats)
    elapsed = time.monotonic() - t0

    for p in written:
        print(p)
    print(f"  source={source_mode} · {len(selected_paths)} reports · outputs={len(written)} · {elapsed:.2f}s", flush=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_base.parent / f"{output_base.name}-consolidated-{ts}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for p in selected_paths:
            tar.add(p, arcname=p.name)
    print(f"  archived → {archive_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
