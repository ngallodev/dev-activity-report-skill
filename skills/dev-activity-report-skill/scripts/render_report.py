#!/usr/bin/env python3
"""Render dev-activity-report JSON into Markdown/HTML outputs."""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Iterable

HTML_CSS = """
<style>
  /* ── Reset & base ─────────────────────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { font-size: 16px; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
    background: #0d1117;
    color: #e6edf3;
    line-height: 1.6;
    padding: 2rem 1rem;
  }

  /* ── Layout ───────────────────────────────────────────────────────────── */
  main { max-width: 860px; margin: 0 auto; }

  /* ── Header ───────────────────────────────────────────────────────────── */
  header.report-header {
    margin-bottom: 2rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid #30363d;
  }
  header.report-header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: #f0f6fc;
    margin-bottom: .25rem;
  }
  header.report-header .subhead { color: #8b949e; font-size: .95rem; margin-bottom: .2rem; }
  .meta { color: #6e7681; font-size: .8rem; }

  /* ── Cards ────────────────────────────────────────────────────────────── */
  article {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
  }
  article h2 {
    font-size: .75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: #8b949e;
    border-bottom: 1px solid #21262d;
    padding-bottom: .5rem;
    margin-bottom: 1rem;
  }
  article h3 {
    font-size: .95rem;
    font-weight: 600;
    color: #79c0ff;
    margin: 1rem 0 .35rem;
  }
  article h3:first-of-type { margin-top: .1rem; }

  /* ── Lists ────────────────────────────────────────────────────────────── */
  ul { list-style: none; padding: 0; }
  ul li {
    position: relative;
    padding-left: 1.1rem;
    margin-bottom: .4rem;
    color: #c9d1d9;
    font-size: .9rem;
    line-height: 1.6;
  }
  ul li::before {
    content: "▸";
    position: absolute;
    left: 0;
    color: #388bfd;
    font-size: .7rem;
    top: .3rem;
  }

  /* ── LinkedIn blockquote ──────────────────────────────────────────────── */
  blockquote.linkedin {
    border-left: 3px solid #388bfd;
    padding: .75rem 1rem;
    background: #1c2433;
    border-radius: 0 6px 6px 0;
    color: #adbac7;
    font-style: italic;
    font-size: .92rem;
    line-height: 1.65;
  }

  /* ── Priority badges ──────────────────────────────────────────────────── */
  .priority-high {
    display: inline-block;
    background: #3d1a1a;
    color: #f85149;
    font-size: .65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .05em;
    padding: .1rem .4rem;
    border-radius: 4px;
    margin-left: .45rem;
    vertical-align: middle;
  }
  .priority-medium {
    display: inline-block;
    background: #2d1f00;
    color: #d29922;
    font-size: .65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .05em;
    padding: .1rem .4rem;
    border-radius: 4px;
    margin-left: .45rem;
    vertical-align: middle;
  }

  /* ── Tables ───────────────────────────────────────────────────────────── */
  table { width: 100%; border-collapse: collapse; font-size: .88rem; }
  thead tr { border-bottom: 1px solid #30363d; }
  th {
    text-align: left;
    padding: .45rem .75rem;
    font-size: .72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: #8b949e;
  }
  td {
    padding: .5rem .75rem;
    border-bottom: 1px solid #21262d;
    color: #c9d1d9;
    vertical-align: top;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1c2128; }

  /* ── Section divider ──────────────────────────────────────────────────── */
  hr.section-divider {
    border: none;
    border-top: 1px dashed #30363d;
    margin: .25rem 0 1rem;
  }
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


def _md_bullets(lines: Iterable[str], indent: str = "") -> str:
    return "\n".join(f"{indent}- {line}" for line in lines)


def _extract_md_section_by_slug(path: Path, slug: str) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    lines = raw.splitlines()
    content: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("### "):
            title = line[4:].strip().lower()
            title_slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-")
            if in_section:
                break
            if title_slug == slug:
                in_section = True
                continue
        if in_section and line.strip():
            content.append(line.rstrip())
    return content


def _read_lines_from_file_url(link: str) -> list[str]:
    if not link or not link.startswith("file://"):
        return []
    parsed = urllib.parse.urlparse(link)
    path = urllib.parse.unquote(parsed.path)
    if not path:
        return []
    slug = parsed.fragment or ""
    file_path = Path(path)
    if not file_path.exists():
        return []
    if slug and file_path.suffix.lower() in {".md", ".markdown"}:
        return _extract_md_section_by_slug(file_path, slug)
    try:
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    if file_path.suffix.lower() in {".html", ".htm"}:
        raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\\1>", " ", raw)
        raw = re.sub(r"(?i)<br\\s*/?>", "\n", raw)
        raw = re.sub(r"(?i)</(p|li|h1|h2|h3|h4|h5|h6|div|section|article)>", "\n", raw)
        raw = re.sub(r"(?s)<[^>]+>", " ", raw)
        raw = html.unescape(raw)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _render_insights_markdown(report: dict) -> str:
    insights = report.get("insights", {}) or {}
    sections = insights.get("sections", []) or []
    quotes = insights.get("quotes", []) or []
    source = insights.get("source", {}) or {}
    if not sections and not quotes:
        return ""

    block = ["## Insights", ""]
    source_link = source.get("log_link") or source.get("report_link") or ""
    if source_link:
        block.append(f"Source: {source_link}")
        block.append("")

    if quotes:
        block.append("### Quotes")
        quote_lines = []
        for item in quotes:
            if not isinstance(item, dict):
                continue
            quote = (item.get("quote") or "").strip()
            link = (item.get("source_link") or item.get("source_path") or "").strip()
            if not quote:
                continue
            if link:
                quote_lines.append(f'"{quote}" ({link})')
            else:
                quote_lines.append(f'"{quote}"')
        block.append(_md_bullets(quote_lines) if quote_lines else "- (none)")
        block.append("")

    if sections:
        block.append("### Sections")
        block.append("")
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = section.get("title") or "Insights"
            link = section.get("link") or section.get("report_link") or ""
            content = section.get("content") or []
            if not isinstance(content, list):
                content = []
            if not content and link:
                content = _read_lines_from_file_url(link)
            block.append(f"#### {title}")
            if link:
                block.append(f"Source: {link}")
            if content:
                block.append(_md_bullets([str(line).strip() for line in content if str(line).strip()]))
            else:
                block.append("- (none)")
            block.append("")

    return "\n".join(line for line in block if line is not None).rstrip()


def _render_insights_html(report: dict) -> str:
    insights = report.get("insights", {}) or {}
    sections = insights.get("sections", []) or []
    quotes = insights.get("quotes", []) or []
    source = insights.get("source", {}) or {}
    if not sections and not quotes:
        return ""

    parts: list[str] = []
    source_link = source.get("log_link") or source.get("report_link") or ""
    if source_link:
        safe_link = html.escape(source_link, quote=True)
        parts.append(f'<p>Source: <a href="{safe_link}">{safe_link}</a></p>')

    if quotes:
        quote_items: list[str] = []
        for item in quotes:
            if not isinstance(item, dict):
                continue
            quote = (item.get("quote") or "").strip()
            link = (item.get("source_link") or item.get("source_path") or "").strip()
            if not quote:
                continue
            safe_quote = html.escape(quote)
            if link:
                safe_link = html.escape(link, quote=True)
                quote_items.append(f'<li>"{safe_quote}" (<a href="{safe_link}">{safe_link}</a>)</li>')
            else:
                quote_items.append(f'<li>"{safe_quote}"</li>')
        if quote_items:
            parts.append("<h3>Quotes</h3>")
            parts.append(f"<ul>{''.join(quote_items)}</ul>")

    if sections:
        parts.append("<h3>Sections</h3>")
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = html.escape(section.get("title") or "Insights")
            link = section.get("link") or section.get("report_link") or ""
            content = section.get("content") or []
            if not isinstance(content, list):
                content = []
            if not content and link:
                content = _read_lines_from_file_url(link)
            parts.append(f"<h4>{title}</h4>")
            if link:
                safe_link = html.escape(link, quote=True)
                parts.append(f'<p>Source: <a href="{safe_link}">{safe_link}</a></p>')
            if content:
                lis = "".join(f"<li>{html.escape(str(line))}</li>" for line in content if str(line).strip())
                parts.append(f"<ul>{lis}</ul>")
            else:
                parts.append("<p>(none)</p>")

    return "\n".join(parts)


def render_markdown(report: dict) -> str:
    generated_at = report.get("generated_at", "")
    resume_header = report.get("resume_header", "")
    sections: list[str] = []

    # ── Title block ──────────────────────────────────────────────────────────
    title_lines = ["# Dev Activity Report"]
    if resume_header:
        title_lines.append(f"**{resume_header}**")
    if generated_at:
        title_lines.append(f"*Generated: {generated_at}*")
    sections.append("\n".join(title_lines))

    # ── Overview ─────────────────────────────────────────────────────────────
    overview = _get_section(report, "overview").get("bullets", [])
    block = ["## Overview", ""]
    block.append(_md_bullets(overview) if overview else "- (none)")
    sections.append("\n".join(block))

    # ── Key Changes ──────────────────────────────────────────────────────────
    key_changes = _get_section(report, "key_changes") or []
    block = ["## Key Changes", ""]
    if key_changes:
        parts = []
        for item in key_changes:
            title = item.get("title") or "(untitled)"
            sub = _ensure_list(item.get("bullets"))
            parts.append(f"### {title}")
            if sub:
                parts.append(_md_bullets(sub))
        block.append("\n\n".join(parts))
    else:
        block.append("- (none)")
    sections.append("\n".join(block))

    # ── Recommendations ───────────────────────────────────────────────────────
    recs = _get_section(report, "recommendations") or []
    block = ["## Recommendations", ""]
    if recs:
        lines = []
        for rec in recs:
            text = rec.get("text", "").rstrip()
            priority = rec.get("priority", "")
            marker = f" `{priority.upper()}`" if priority in ("high", "medium") else ""
            lines.append(f"- {text}{marker}")
        block.append("\n".join(lines))
    else:
        block.append("- (none)")
    sections.append("\n".join(block))

    # ── Resume Bullets ────────────────────────────────────────────────────────
    resume = _get_section(report, "resume_bullets") or []
    block = ["## Resume Bullets", ""]
    if resume:
        block.append(_md_bullets(rb.get("text", "").rstrip() for rb in resume))
    else:
        block.append("- (none)")
    sections.append("\n".join(block))

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    linkedin = _get_section(report, "linkedin").get("sentences", [])
    block = ["## LinkedIn", ""]
    if linkedin:
        text = " ".join(s.strip() for s in linkedin if s)
        block.append(f"> {text}")
    else:
        block.append("(none)")
    sections.append("\n".join(block))

    # ── Highlights ────────────────────────────────────────────────────────────
    highlights = _get_section(report, "highlights") or []
    block = ["## Highlights", ""]
    if highlights:
        lines = []
        for h in highlights:
            t = h.get("title", "").rstrip()
            r = h.get("rationale", "").rstrip()
            lines.append(f"- **{t}** — {r}" if r else f"- **{t}**")
        block.append("\n".join(lines))
    else:
        block.append("- (none)")
    sections.append("\n".join(block))

    insights_md = _render_insights_markdown(report)
    if insights_md:
        sections.append(insights_md)

    # ── Timeline ──────────────────────────────────────────────────────────────
    timeline = _get_section(report, "timeline") or []
    block = ["## Timeline", ""]
    if timeline:
        rows = ["| Date | Event |", "|:---|:---|"]
        for row in timeline:
            rows.append(f"| {row.get('date', '')} | {row.get('event', '')} |")
        block.append("\n".join(rows))
    else:
        block.append("- (none)")
    sections.append("\n".join(block))

    # ── Tech Inventory ────────────────────────────────────────────────────────
    tech = _get_section(report, "tech_inventory") or {}
    block = ["## Tech Inventory", ""]
    if tech:
        rows = ["| Category | Items |", "|:---|:---|"]
        for label, key in (
            ("Languages", "languages"),
            ("Frameworks / Libs", "frameworks"),
            ("AI Tools", "ai_tools"),
            ("Infra / Tooling", "infra"),
        ):
            items = ", ".join(_ensure_list(tech.get(key)))
            if items:
                rows.append(f"| {label} | {items} |")
        block.append("\n".join(rows))
    else:
        block.append("- (none)")
    sections.append("\n".join(block))

    return "\n\n---\n\n".join(sections) + "\n"


def render_html(report: dict) -> str:
    generated_at = report.get("generated_at") or datetime.utcnow().isoformat() + "Z"
    resume_header = report.get("resume_header", "Dev Activity Report")

    def ul(items: Iterable[str]) -> str:
        lst = list(items)
        if not lst:
            return "<p>(none)</p>"
        lis = "".join(f"<li>{item}</li>" for item in lst)
        return f"<ul>{lis}</ul>"

    def article(title: str, body: str) -> str:
        return f'<article>\n<h2>{title}</h2>\n{body}\n</article>'

    # Overview
    overview_html = ul(_get_section(report, "overview").get("bullets", []))

    # Key Changes
    key_changes = _get_section(report, "key_changes") or []
    if key_changes:
        parts = []
        for item in key_changes:
            t = item.get("title") or "(untitled)"
            sub = _ensure_list(item.get("bullets"))
            parts.append(f"<h3>{t}</h3>{ul(sub)}")
        key_changes_html = "\n".join(parts)
    else:
        key_changes_html = "<p>(none)</p>"

    # Recommendations
    recs = _get_section(report, "recommendations") or []
    if recs:
        lis = []
        for r in recs:
            text = r.get("text", "")
            priority = r.get("priority", "")
            badge = ""
            if priority == "high":
                badge = '<span class="priority-high">high</span>'
            elif priority == "medium":
                badge = '<span class="priority-medium">medium</span>'
            lis.append(f"<li>{text}{badge}</li>")
        recs_html = f"<ul>{''.join(lis)}</ul>"
    else:
        recs_html = "<p>(none)</p>"

    # Resume Bullets
    resume = _get_section(report, "resume_bullets") or []
    resume_html = ul(r.get("text", "") for r in resume)

    # LinkedIn
    linkedin_sentences = _get_section(report, "linkedin").get("sentences", [])
    if linkedin_sentences:
        text = " ".join(s.strip() for s in linkedin_sentences if s)
        linkedin_html = f'<blockquote class="linkedin">{text}</blockquote>'
    else:
        linkedin_html = "<p>(none)</p>"

    # Highlights
    highlights = _get_section(report, "highlights") or []
    if highlights:
        lis = []
        for h in highlights:
            t = h.get("title", "")
            r = h.get("rationale", "")
            lis.append(f"<li><strong>{t}</strong> — {r}</li>" if r else f"<li><strong>{t}</strong></li>")
        highlights_html = f"<ul>{''.join(lis)}</ul>"
    else:
        highlights_html = "<p>(none)</p>"

    insights_html = _render_insights_html(report)

    # Timeline
    timeline = _get_section(report, "timeline") or []
    if timeline:
        rows = "".join(
            f"<tr><td>{r.get('date','')}</td><td>{r.get('event','')}</td></tr>"
            for r in timeline
        )
        timeline_html = (
            "<table><thead><tr><th>Date</th><th>Event</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        timeline_html = "<p>(none)</p>"

    # Tech Inventory
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
            if items:
                rows.append(f"<tr><td>{label}</td><td>{items}</td></tr>")
        tech_html = (
            "<table><thead><tr><th>Category</th><th>Items</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    else:
        tech_html = "<p>(none)</p>"

    body = "\n".join([
        article("Overview", overview_html),
        article("Key Changes", key_changes_html),
        article("Recommendations", recs_html),
        '<hr class="section-divider">',
        article("Resume Bullets", resume_html),
        article("LinkedIn", linkedin_html),
        '<hr class="section-divider">',
        article("Highlights", highlights_html),
        article("Insights", insights_html) if insights_html else "",
        article("Timeline", timeline_html),
        article("Tech Inventory", tech_html),
    ])

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dev Activity Report</title>
  {HTML_CSS}
</head>
<body>
  <main class="container">
    <header class="report-header">
      <h1>Dev Activity Report</h1>
      <div class="subhead">{resume_header}</div>
      <p class="meta">Generated: {generated_at}</p>
    </header>
    {body}
  </main>
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
