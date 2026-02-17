#!/usr/bin/env python3
"""Render dev-activity-report JSON into Markdown/HTML outputs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

HTML_CSS = """
<link rel="stylesheet" href="https://unpkg.com/@picocss/pico@2/css/pico.min.css">
<style>
  :root { --pico-font-size: 100%; }
  main { max-width: 980px; }
  .meta { color: #6b7280; font-size: 0.9rem; }
  .pill { display: inline-block; padding: 0.15rem 0.45rem; border: 1px solid #e5e7eb; border-radius: 999px; font-size: 0.8rem; margin-right: 0.35rem; }
  .section { margin-bottom: 2rem; }
  table { font-size: 0.95rem; }
</style>
""".strip()


def _ensure_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get_section(report: dict, name: str) -> dict:
    return report.get("sections", {}).get(name, {}) or {}


def _md_list(lines: Iterable[str]) -> str:
    return "\\n".join(f"- {line}" for line in lines)


def render_markdown(report: dict) -> str:
    out = []

    overview = _get_section(report, "overview").get("bullets", [])
    out.append("## Overview")
    out.append(_md_list(overview) if overview else "- (none)")

    out.append("\\n## Key Changes")
    key_changes = _get_section(report, "key_changes") or []
    if key_changes:
        for item in key_changes:
            title = item.get("title") or "(untitled)"
            out.append(f"- **{title}**")
            bullets = _ensure_list(item.get("bullets"))
            for bullet in bullets:
                out.append(f"  - {bullet}")
    else:
        out.append("- (none)")

    out.append("\\n## Recommendations")
    recs = _get_section(report, "recommendations") or []
    if recs:
        for rec in recs:
            text = rec.get("text") or ""
            out.append(f"- {text}".rstrip())
    else:
        out.append("- (none)")

    out.append("\\n## Resume Bullets")
    resume = _get_section(report, "resume_bullets") or []
    if resume:
        for rb in resume:
            out.append(f"- {rb.get('text', '')}".rstrip())
    else:
        out.append("- (none)")

    out.append("\\n## LinkedIn")
    linkedin = _get_section(report, "linkedin").get("sentences", [])
    if linkedin:
        out.append(" ".join(s.strip() for s in linkedin if s))
    else:
        out.append("(none)")

    out.append("\\n## Highlights")
    highlights = _get_section(report, "highlights") or []
    if highlights:
        for h in highlights:
            title = h.get("title") or ""
            rationale = h.get("rationale") or ""
            out.append(f"- **{title}** - {rationale}".rstrip(" -"))
    else:
        out.append("- (none)")

    out.append("\\n## Timeline")
    timeline = _get_section(report, "timeline") or []
    if timeline:
        out.append("| Date | Event |")
        out.append("|---|---|")
        for row in timeline:
            date = row.get("date", "")
            event = row.get("event", "")
            out.append(f"| {date} | {event} |")
    else:
        out.append("- (none)")

    out.append("\\n## Tech Inventory")
    tech = _get_section(report, "tech_inventory") or {}
    if tech:
        out.append("| Category | Items |")
        out.append("|---|---|")
        for label, key in (
            ("Languages", "languages"),
            ("Frameworks / Libs", "frameworks"),
            ("AI Tools", "ai_tools"),
            ("Infra / Tooling", "infra"),
        ):
            items = ", ".join(_ensure_list(tech.get(key)))
            out.append(f"| {label} | {items} |")
    else:
        out.append("- (none)")

    return "\\n".join(out).strip() + "\\n"


def render_html(report: dict) -> str:
    generated_at = report.get("generated_at") or datetime.utcnow().isoformat() + "Z"

    def bullets(items: Iterable[str]) -> str:
        if not items:
            return "<p>(none)</p>"
        lis = "".join(f"<li>{item}</li>" for item in items)
        return f"<ul>{lis}</ul>"

    def card(title: str, body: str) -> str:
        return f"<section class=\"section\"><h2>{title}</h2>{body}</section>"

    overview = bullets(_get_section(report, "overview").get("bullets", []))

    key_changes = _get_section(report, "key_changes") or []
    if key_changes:
        parts = []
        for item in key_changes:
            title = item.get("title") or "(untitled)"
            items = _ensure_list(item.get("bullets"))
            parts.append(f"<h3>{title}</h3>{bullets(items)}")
        key_changes_html = "".join(parts)
    else:
        key_changes_html = "<p>(none)</p>"

    recs = _get_section(report, "recommendations") or []
    recs_html = bullets([r.get("text", "") for r in recs])

    resume = _get_section(report, "resume_bullets") or []
    resume_html = bullets([r.get("text", "") for r in resume])

    linkedin_sentences = _get_section(report, "linkedin").get("sentences", [])
    linkedin_html = (
        f"<p>{' '.join(s.strip() for s in linkedin_sentences if s)}</p>"
        if linkedin_sentences
        else "<p>(none)</p>"
    )

    highlights = _get_section(report, "highlights") or []
    highlights_html = "".join(
        f"<li><strong>{h.get('title','')}</strong> - {h.get('rationale','')}</li>" for h in highlights
    )
    highlights_html = f"<ul>{highlights_html}</ul>" if highlights else "<p>(none)</p>"

    timeline = _get_section(report, "timeline") or []
    if timeline:
        rows = "".join(
            f"<tr><td>{r.get('date','')}</td><td>{r.get('event','')}</td></tr>" for r in timeline
        )
        timeline_html = (
            "<table><thead><tr><th>Date</th><th>Event</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        timeline_html = "<p>(none)</p>"

    tech = _get_section(report, "tech_inventory") or {}
    if tech:
        rows = []
        for label, key in (
            ("Languages", "languages"),
            ("Frameworks / Libs", "frameworks"),
            ("AI Tools", "ai_tools"),
            ("Infra / Tooling", "infra"),
        ):
            items = ", ".join(_ensure_list(tech.get(key)))
            rows.append(f"<tr><td>{label}</td><td>{items}</td></tr>")
        tech_html = (
            "<table><thead><tr><th>Category</th><th>Items</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    else:
        tech_html = "<p>(none)</p>"

    body = "\n".join(
        [
            f"<p class=\"meta\">Generated at {generated_at}</p>",
            card("Overview", overview),
            card("Key Changes", key_changes_html),
            card("Recommendations", recs_html),
            card("Resume Bullets", resume_html),
            card("LinkedIn", linkedin_html),
            card("Highlights", highlights_html),
            card("Timeline", timeline_html),
            card("Tech Inventory", tech_html),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dev Activity Report</title>
  {HTML_CSS}
</head>
<body>
  <main class="container">{body}</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render dev-activity-report JSON to Markdown/HTML.")
    parser.add_argument("--input", required=True, type=Path, help="Phase 2 JSON input file")
    parser.add_argument("--output-dir", required=True, type=Path, help="Output directory")
    parser.add_argument("--base-name", required=True, help="Base filename (no extension)")
    parser.add_argument("--formats", default="md", help="Comma-separated output formats: md,html")
    args = parser.parse_args()

    report = json.loads(args.input.read_text(encoding="utf-8"))
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if "md" in formats:
        md_text = render_markdown(report)
        (args.output_dir / f"{args.base_name}.md").write_text(md_text, encoding="utf-8")

    if "html" in formats:
        html_text = render_html(report)
        (args.output_dir / f"{args.base_name}.html").write_text(html_text, encoding="utf-8")


if __name__ == "__main__":
    main()
