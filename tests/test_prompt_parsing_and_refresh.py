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
