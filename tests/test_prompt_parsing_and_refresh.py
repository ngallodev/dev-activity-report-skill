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
        monkeypatch.setattr(
            run_pipeline,
            "extract_insights_quotes",
            lambda env, claude_bin=None, codex_bin=None: ("", ""),
        )

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

    def test_phase2_routes_to_codex_for_openai_model_when_use_codex_true(self, monkeypatch):
        import run_pipeline

        called = {"codex": 0, "claude": 0}

        def fake_codex(prompt, model, codex_bin, env=None, sandbox="workspace-write", system_prompt=None, timeout=300):
            called["codex"] += 1
            return "{}", {"prompt_tokens": 0, "completion_tokens": 0}

        def fake_claude(prompt, model, claude_bin, system_prompt=None, timeout=300, max_tokens=2048):
            called["claude"] += 1
            return "{}", {"prompt_tokens": 1, "completion_tokens": 1}

        monkeypatch.setattr(run_pipeline, "codex_exec_call", fake_codex)
        monkeypatch.setattr(run_pipeline, "claude_call", fake_claude)
        monkeypatch.setattr(
            run_pipeline,
            "extract_insights_quotes",
            lambda env, claude_bin=None, codex_bin=None: ("", ""),
        )
        monkeypatch.setattr(
            run_pipeline,
            "extract_insights_quote_entries",
            lambda env, claude_bin=None, codex_bin=None: ([], ""),
        )

        env = {
            "USE_CODEX": "true",
            "PHASE2_MODEL": "gpt-5.1-codex-mini",
        }
        run_pipeline.call_phase2(
            "{}",
            "- draft",
            env,
            claude_bin="/usr/bin/claude",
            codex_bin="/usr/bin/codex",
        )
        assert called["codex"] == 1
        assert called["claude"] == 0

    def test_extract_insights_quotes_opt_in(self, tmp_path):
        import run_pipeline
        import unittest.mock as mock

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
        def fake_model_call(prompt, model, env, claude_bin=None, codex_bin=None, system_prompt=None, timeout=300):
            return '{"quotes":["Delivered two complex automation upgrades."]}', {}

        with mock.patch.object(run_pipeline, "call_model", fake_model_call):
            block, source = run_pipeline.extract_insights_quotes(env, claude_bin="/usr/bin/claude")
        assert "Delivered two complex automation upgrades." in block
        assert source == str(html_file)

    def test_extract_insights_quote_entries_opt_in(self, tmp_path):
        import run_pipeline
        import unittest.mock as mock

        html_file = tmp_path / "report.html"
        html_file.write_text(
            "<html><body><p>Workflow outcomes improved after automation cleanup.</p></body></html>",
            encoding="utf-8",
        )
        env = {
            "INCLUDE_CLAUDE_INSIGHTS_QUOTES": "true",
            "INSIGHTS_REPORT_PATH": str(html_file),
            "CLAUDE_INSIGHTS_QUOTES_MAX": "3",
            "CLAUDE_INSIGHTS_QUOTES_MAX_CHARS": "500",
        }
        def fake_model_call(prompt, model, env, claude_bin=None, codex_bin=None, system_prompt=None, timeout=300):
            return '{"quotes":["Workflow outcomes improved after automation cleanup."]}', {}

        with mock.patch.object(run_pipeline, "call_model", fake_model_call):
            entries, source = run_pipeline.extract_insights_quote_entries(env, claude_bin="/usr/bin/claude")
        assert entries
        assert entries[0]["quote"].startswith("Workflow outcomes")
        assert entries[0]["source_path"] == str(html_file)
        assert entries[0]["source_link"].startswith("file://")
        assert source == str(html_file)

    def test_extract_insights_quotes_no_heuristic_fallback_by_default(self, tmp_path):
        import run_pipeline

        html_file = tmp_path / "report.html"
        html_file.write_text(
            "<html><body><p>Workflow outcomes improved after automation cleanup.</p></body></html>",
            encoding="utf-8",
        )
        env = {
            "INCLUDE_CLAUDE_INSIGHTS_QUOTES": "true",
            "INSIGHTS_REPORT_PATH": str(html_file),
        }
        entries, source = run_pipeline.extract_insights_quote_entries(env)
        assert entries == []
        assert source == str(html_file)

    def test_parse_insights_sections(self):
        import run_pipeline

        env = {"INSIGHTS_REPORT_PATH": "/tmp/report.html"}
        parsed = run_pipeline.parse_insights_sections(
            [
                "## 2026-02-18",
                "### Wins",
                "- Improved report quality",
                "### Friction",
                "- Missing quote links",
            ],
            env,
        )
        assert parsed["sections"]
        assert parsed["sections"][0]["id"] == "wins"
        assert parsed["sections"][0]["entry_date"] == "2026-02-18"


class TestPhase15ThoroughMode:
    """PHASE15_THOROUGH flag switches between terse and thorough prompt paths."""

    SUMMARY = {"p": [{"n": "demo", "cc": 3, "hl": ["bugfix"]}]}

    def test_terse_prompt_default(self):
        from phase1_5_draft import build_prompt, TERSE_PROMPT

        prompt = build_prompt(self.SUMMARY, {})
        assert TERSE_PROMPT in prompt
        assert "5–8 bullets" in prompt
        assert "lowlight" not in prompt.lower()

    def test_thorough_prompt_when_flag_set(self):
        from phase1_5_draft import build_prompt, THOROUGH_PROMPT

        for val in ("true", "1", "yes", "on"):
            prompt = build_prompt(self.SUMMARY, {"PHASE15_THOROUGH": val})
            assert THOROUGH_PROMPT in prompt
            assert "lowlight" in prompt.lower()
            assert "watch-out" in prompt.lower()

    def test_thorough_false_still_terse(self):
        from phase1_5_draft import build_prompt, TERSE_PROMPT

        prompt = build_prompt(self.SUMMARY, {"PHASE15_THOROUGH": "false"})
        assert TERSE_PROMPT in prompt

    def test_summary_always_appended_last(self):
        from phase1_5_draft import build_prompt

        for thorough in ("false", "true"):
            prompt = build_prompt(self.SUMMARY, {"PHASE15_THOROUGH": thorough})
            assert prompt.endswith(
                "Summary JSON (read-only context; do not rewrite it):\n"
                + __import__("json").dumps(self.SUMMARY, separators=(",", ":"))
            )

    def test_run_pipeline_terse_prompt(self):
        from run_pipeline import PHASE15_TERSE_TMPL, call_phase15_claude

        captured = {}

        import run_pipeline
        original = run_pipeline.claude_call

        def fake_call(prompt, model, claude_bin, system_prompt=None, timeout=180):
            captured["prompt"] = prompt
            return "- bullet", {}

        import unittest.mock as mock
        with mock.patch.object(run_pipeline, "claude_call", fake_call):
            call_phase15_claude(self.SUMMARY, {}, "/usr/bin/claude")

        assert PHASE15_TERSE_TMPL in captured["prompt"]
        assert "lowlight" not in captured["prompt"].lower()

    def test_run_pipeline_phase15_routes_to_codex_for_openai_model_when_use_codex_true(self):
        import run_pipeline
        import unittest.mock as mock

        called = {"codex": 0, "claude": 0}

        def fake_codex(prompt, model, codex_bin, env=None, sandbox="workspace-write", system_prompt=None, timeout=300):
            called["codex"] += 1
            return "- bullet", {"prompt_tokens": 0, "completion_tokens": 0}

        def fake_claude(prompt, model, claude_bin, system_prompt=None, timeout=300, max_tokens=2048):
            called["claude"] += 1
            return "- bullet", {"prompt_tokens": 1, "completion_tokens": 1}

        with mock.patch.object(run_pipeline, "codex_exec_call", fake_codex):
            with mock.patch.object(run_pipeline, "claude_call", fake_claude):
                run_pipeline.call_phase15_claude(
                    self.SUMMARY,
                    {"USE_CODEX": "true", "PHASE15_MODEL": "gpt-5.1-codex-mini"},
                    claude_bin="/usr/bin/claude",
                    codex_bin="/usr/bin/codex",
                )

        assert called["codex"] == 1
        assert called["claude"] == 0

    def test_run_pipeline_thorough_prompt(self):
        from run_pipeline import PHASE15_THOROUGH_TMPL, call_phase15_claude

        captured = {}

        import run_pipeline
        import unittest.mock as mock

        def fake_call(prompt, model, claude_bin, system_prompt=None, timeout=180):
            captured["prompt"] = prompt
            return "- bullet", {}

        with mock.patch.object(run_pipeline, "claude_call", fake_call):
            call_phase15_claude(self.SUMMARY, {"PHASE15_THOROUGH": "true"}, "/usr/bin/claude")

        assert PHASE15_THOROUGH_TMPL in captured["prompt"]
        assert "lowlight" in captured["prompt"].lower()
        assert "watch-out" in captured["prompt"].lower()


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


class TestRunReportContracts:
    """Regression checks for run_report.sh runtime contract."""

    def test_setup_env_uses_supported_flags(self):
        script = Path("skills/dev-activity-report-skill/scripts/run_report.sh").read_text(encoding="utf-8")
        assert "--non-interactive" not in script
        assert 'python3 "$SKILL_DIR/scripts/setup_env.py"' in script

    def test_codex_phase25_merges_insights_metadata(self):
        script = Path("skills/dev-activity-report-skill/scripts/run_report.sh").read_text(encoding="utf-8")
        assert "parse_insights_sections" in script
        assert "extract_insights_quote_entries" in script
        assert '"insights": {' in script
