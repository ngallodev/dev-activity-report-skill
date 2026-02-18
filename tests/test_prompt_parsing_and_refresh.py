"""
Parser hardening and thorough refresh utility tests.
"""

import json
from pathlib import Path

import pytest


class TestPhase2JsonParsing:
    """Phase 2 parser tolerates fenced/wrapped model output."""

    def test_parse_plain_json_object(self):
        from run_pipeline import parse_llm_json_output

        raw = '{"sections":{"overview":{"bullets":["ok"]}},"render_hints":{}}'
        parsed = parse_llm_json_output(raw)
        assert parsed["sections"]["overview"]["bullets"] == ["ok"]

    def test_parse_fenced_json_object(self):
        from run_pipeline import parse_llm_json_output

        raw = "```json\n{\"sections\":{\"overview\":{\"bullets\":[\"ok\"]}},\"render_hints\":{}}\n```"
        parsed = parse_llm_json_output(raw)
        assert parsed["sections"]["overview"]["bullets"] == ["ok"]

    def test_parse_prefixed_text_then_json(self):
        from run_pipeline import parse_llm_json_output

        raw = "Here is the report JSON:\n{\"sections\":{\"overview\":{\"bullets\":[\"ok\"]}},\"render_hints\":{}}"
        parsed = parse_llm_json_output(raw)
        assert "sections" in parsed

    def test_rejects_top_level_array(self):
        from run_pipeline import parse_llm_json_output

        with pytest.raises(json.JSONDecodeError):
            parse_llm_json_output('[{"not":"an object"}]')

    def test_phase15_prompt_injects_summary_after_custom_rules(self):
        from phase1_5_draft import build_prompt

        env = {"PHASE15_RULES_EXTRA": "Prefer impact-first bullets."}
        prompt = build_prompt({"p": [{"n": "demo"}]}, env)
        assert "Additional user rules from .env" in prompt
        assert "Summary JSON (read-only context; do not rewrite it):" in prompt
        assert prompt.rfind("Summary JSON (read-only context; do not rewrite it):") > prompt.rfind(
            "Additional user rules from .env"
        )

    def test_phase2_uses_rules_extra_without_schema_loss(self, monkeypatch):
        import run_pipeline

        captured = {}

        def fake_claude_call(prompt, model, claude_bin, system_prompt=None, timeout=300):
            captured["prompt"] = prompt
            return "{}", {"prompt_tokens": 1, "completion_tokens": 1}

        monkeypatch.setattr(run_pipeline, "claude_call", fake_claude_call)
        monkeypatch.setattr(run_pipeline, "extract_insights_quotes", lambda env: ("", ""))

        env = {
            "RESUME_HEADER": "Name, Jan 2025 - Present",
            "PHASE2_MODEL": "sonnet",
            "PHASE2_RULES_EXTRA": "Use exactly 7 resume bullets.",
        }
        run_pipeline.call_phase2("{}", "- draft", env, "/usr/bin/claude")
        prompt = captured["prompt"]
        assert "Use exactly 7 resume bullets." in prompt
        assert '"sections"' in prompt
        assert "Summary JSON (compact):" in prompt
        assert "Draft bullets:" in prompt

    def test_extract_insights_quotes_opt_in(self, tmp_path):
        import run_pipeline

        html_file = tmp_path / "report.html"
        html_file.write_text(
            "<html><body><h2>Wins</h2><p>Delivered two complex automation upgrades.</p>"
            "<p>Improved reliability and observability across workflows.</p></body></html>",
            encoding="utf-8",
        )
        env = {
            "INCLUDE_CLAUDE_INSIGHTS_QUOTES": "true",
            "INSIGHTS_REPORT_PATH": str(html_file),
            "CLAUDE_INSIGHTS_QUOTES_MAX": "3",
            "CLAUDE_INSIGHTS_QUOTES_MAX_CHARS": "500",
        }
        block, source = run_pipeline.extract_insights_quotes(env)
        assert "Delivered two complex automation upgrades." in block
        assert source == str(html_file)


class TestThoroughRefresh:
    """Refresh utility computes expected marker/cache actions."""

    def test_resolve_roots_prefers_apps_dirs(self):
        from thorough_refresh import resolve_roots

        env = {"APPS_DIRS": "~/apps-a ~/apps-b", "APPS_DIR": "~/apps-c"}
        roots = resolve_roots(env, cli_roots=[])
        assert len(roots) == 2
        assert str(roots[0]).endswith("/apps-a")
        assert str(roots[1]).endswith("/apps-b")

    def test_collect_skill_cache_targets(self, tmp_path):
        from thorough_refresh import Plan, collect_skill_cache_targets

        skill = tmp_path / "skill"
        scripts = skill / "scripts"
        scripts.mkdir(parents=True)
        (skill / ".phase1-cache.json").write_text("{}")
        (scripts / ".phase1-cache.tmp").write_text("{}")
        (skill / ".dev-report-cache.md").write_text("fp")

        plan = Plan()
        collect_skill_cache_targets(plan, skill)
        targets = {p.name for p in plan.delete_files}
        assert ".phase1-cache.json" in targets
        assert ".phase1-cache.tmp" in targets
        assert ".dev-report-cache.md" in targets

    def test_collect_marker_actions_promotes_fork_and_clears_not_my_work(self, tmp_path):
        from thorough_refresh import Plan, collect_marker_actions

        root = tmp_path / "apps"
        project = root / "forked-project"
        project.mkdir(parents=True)
        (project / ".forked-work").touch()
        (project / ".not-my-work").touch()

        plan = Plan()
        collect_marker_actions(
            plan=plan,
            roots=[root],
            clear_skip=False,
            clear_not_my_work_all=False,
            clear_not_my_work_forked=True,
        )

        assert (project / ".forked-work-modified") in plan.touch_files
        assert (project / ".not-my-work") in plan.delete_files
