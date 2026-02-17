"""
Test Group: Render Output

Protects against:
- Malformed Phase 2 output crashing renderer
- Missing sections in output
- HTML/CSS injection issues
- Output file generation

Justification: Render is the final phase. Failures here mean the entire
pipeline produces no usable output despite successful LLM calls.
"""

import json
from pathlib import Path
import pytest


class TestMarkdownRendering:
    """Markdown output must be correctly generated."""

    def test_basic_markdown_render(self, tmp_path):
        """Valid input must produce valid Markdown."""
        from render_report import render_markdown

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "resume_header": "Developer, Jan 2024 – Present",
            "sections": {
                "overview": {"bullets": ["Shipped feature X", "Fixed critical bug Y"]},
                "key_changes": [
                    {
                        "title": "Feature X",
                        "bullets": ["Implemented core functionality", "Added tests"],
                    }
                ],
                "recommendations": [
                    {"text": "Refactor module A", "priority": "high"},
                    {"text": "Update documentation", "priority": "medium"},
                ],
                "resume_bullets": [
                    {"text": "Led development of feature X"},
                    {"text": "Reduced latency by 50%"},
                ],
                "linkedin": {
                    "sentences": ["Excited to share my recent work on feature X."]
                },
                "highlights": [
                    {
                        "title": "Performance Improvement",
                        "rationale": "Reduced P99 latency",
                    }
                ],
                "timeline": [{"date": "2024-01-15", "event": "Launched feature X"}],
                "tech_inventory": {
                    "languages": ["Python", "TypeScript"],
                    "frameworks": ["FastAPI", "React"],
                    "ai_tools": ["Claude", "OpenAI"],
                    "infra": ["Docker", "AWS"],
                },
            },
        }

        md = render_markdown(report)

        # Check structure
        assert "# Dev Activity Report" in md
        assert "**Developer, Jan 2024 – Present**" in md
        assert "Shipped feature X" in md
        assert "Refactor module A `HIGH`" in md
        assert "## Overview" in md
        assert "## Key Changes" in md
        assert "## Tech Inventory" in md

    def test_empty_sections_handled(self):
        """Empty or missing sections must not crash renderer."""
        from render_report import render_markdown

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "sections": {
                "overview": {"bullets": []},
                "key_changes": [],
                "recommendations": [],
                "resume_bullets": [],
                "linkedin": {"sentences": []},
                "highlights": [],
                "timeline": [],
                "tech_inventory": {},
            },
        }

        md = render_markdown(report)

        # Should still produce valid markdown
        assert "# Dev Activity Report" in md
        assert "- (none)" in md  # Placeholder for empty sections

    def test_missing_sections_key_handled(self):
        """Missing 'sections' key must not crash."""
        from render_report import render_markdown

        report = {"generated_at": "2024-01-15T10:00:00Z"}

        md = render_markdown(report)

        assert "# Dev Activity Report" in md

    def test_malformed_bullets_handled(self):
        """Malformed bullet items must not crash renderer."""
        from render_report import render_markdown

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "sections": {
                "overview": {"bullets": ["Valid bullet", None, 123, "Another valid"]}
            },
        }

        # Should handle mixed types gracefully
        md = render_markdown(report)
        assert "Valid bullet" in md

    def test_special_characters_escaped(self):
        """Special Markdown characters should be handled."""
        from render_report import render_markdown

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "sections": {
                "overview": {
                    "bullets": [
                        "Use `code` blocks",
                        "Handle <html> tags",
                        "Deal with **bold** text",
                    ]
                }
            },
        }

        md = render_markdown(report)

        # Content should be preserved
        assert "`code`" in md
        assert "<html>" in md
        assert "**bold**" in md


class TestHTMLRendering:
    """HTML output must be correctly generated."""

    def test_basic_html_render(self, tmp_path):
        """Valid input must produce valid HTML."""
        from render_report import render_html

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "resume_header": "Developer, Jan 2024 – Present",
            "sections": {
                "overview": {"bullets": ["Shipped feature X"]},
                "key_changes": [{"title": "Feature X", "bullets": ["Implemented"]}],
                "recommendations": [{"text": "Refactor", "priority": "high"}],
                "resume_bullets": [{"text": "Led development"}],
                "linkedin": {"sentences": ["Excited to share."]},
                "highlights": [{"title": "Performance", "rationale": "Improved"}],
                "timeline": [{"date": "2024-01-15", "event": "Launch"}],
                "tech_inventory": {
                    "languages": ["Python"],
                    "frameworks": [],
                    "ai_tools": [],
                    "infra": [],
                },
            },
        }

        html = render_html(report)

        # Check structure
        assert "<!doctype html>" in html.lower()
        assert "<html" in html
        assert "Dev Activity Report" in html
        assert "Shipped feature X" in html
        assert "<article>" in html
        assert "<style>" in html

    def test_priority_badges_rendered(self):
        """High/medium priority badges must be rendered."""
        from render_report import render_html

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "sections": {
                "recommendations": [
                    {"text": "Critical fix", "priority": "high"},
                    {"text": "Nice to have", "priority": "medium"},
                    {"text": "Low priority", "priority": "low"},
                ]
            },
        }

        html = render_html(report)

        assert "priority-high" in html
        assert "priority-medium" in html
        assert "HIGH" in html.upper()

    def test_empty_html_sections(self):
        """Empty sections must render as '(none)'."""
        from render_report import render_html

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "sections": {
                "overview": {"bullets": []},
                "key_changes": [],
                "recommendations": [],
                "resume_bullets": [],
                "linkedin": {"sentences": []},
                "highlights": [],
                "timeline": [],
                "tech_inventory": {},
            },
        }

        html = render_html(report)

        assert "<p>(none)</p>" in html

    def test_linkedin_blockquote_rendered(self):
        """LinkedIn content must be in blockquote."""
        from render_report import render_html

        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "sections": {
                "linkedin": {"sentences": ["First sentence.", "Second sentence."]}
            },
        }

        html = render_html(report)

        assert '<blockquote class="linkedin">' in html
        assert "First sentence." in html


class TestRenderCommandLine:
    """Command-line interface must work correctly."""

    def test_render_main_md_only(self, tmp_path):
        """--formats md must produce only markdown file."""
        from render_report import main
        import argparse

        # Create test input
        input_file = tmp_path / "input.json"
        input_file.write_text(
            json.dumps(
                {
                    "generated_at": "2024-01-15T10:00:00Z",
                    "sections": {"overview": {"bullets": ["Test"]}},
                }
            )
        )

        output_dir = tmp_path / "output"

        # Parse args manually
        import sys

        old_argv = sys.argv
        try:
            sys.argv = [
                "render_report.py",
                "--input",
                str(input_file),
                "--output-dir",
                str(output_dir),
                "--base-name",
                "test-report",
                "--formats",
                "md",
            ]
            main()
        finally:
            sys.argv = old_argv

        # Check output
        assert (output_dir / "test-report.md").exists()
        assert not (output_dir / "test-report.html").exists()

    def test_render_main_both_formats(self, tmp_path):
        """--formats md,html must produce both files."""
        from render_report import main
        import sys

        input_file = tmp_path / "input.json"
        input_file.write_text(
            json.dumps(
                {
                    "generated_at": "2024-01-15T10:00:00Z",
                    "sections": {"overview": {"bullets": ["Test"]}},
                }
            )
        )

        output_dir = tmp_path / "output"

        old_argv = sys.argv
        try:
            sys.argv = [
                "render_report.py",
                "--input",
                str(input_file),
                "--output-dir",
                str(output_dir),
                "--base-name",
                "test-report",
                "--formats",
                "md,html",
            ]
            main()
        finally:
            sys.argv = old_argv

        assert (output_dir / "test-report.md").exists()
        assert (output_dir / "test-report.html").exists()

    def test_render_output_dir_created(self, tmp_path):
        """Output directory must be created if it doesn't exist."""
        from render_report import main
        import sys

        input_file = tmp_path / "input.json"
        input_file.write_text(
            json.dumps(
                {
                    "generated_at": "2024-01-15T10:00:00Z",
                    "sections": {"overview": {"bullets": ["Test"]}},
                }
            )
        )

        # Non-existent output directory
        output_dir = tmp_path / "new" / "nested" / "output"

        old_argv = sys.argv
        try:
            sys.argv = [
                "render_report.py",
                "--input",
                str(input_file),
                "--output-dir",
                str(output_dir),
                "--base-name",
                "test",
                "--formats",
                "md",
            ]
            main()
        finally:
            sys.argv = old_argv

        assert output_dir.exists()
        assert (output_dir / "test.md").exists()
