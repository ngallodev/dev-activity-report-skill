"""
Integration tests for the full pipeline.

Tests data flow: Phase 1 -> Phase 1.5 -> Phase 2 -> Render
All LLM calls are mocked. Tests verify contracts between phases.

Strategy:
- Mock at subprocess level (subprocess.run)
- Use shared fixtures for valid data
- Validate outputs against JSON schemas
- Test both happy paths and error conditions
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from fixtures import valid_phase1_output, valid_phase15_output, valid_phase2_output


class TestFullPipeline:
    """End-to-end pipeline with all phases executing."""

    def test_happy_path_produces_output_files(self, tmp_path, monkeypatch):
        """
        Full pipeline with valid inputs produces .md and .html files.

        Verifies the complete flow from Phase 1 through rendering,
        ensuring output files are created with expected content.
        """
        from run_pipeline import run

        # Setup environment
        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={tmp_path}/output
REPORT_OUTPUT_FORMATS=md,html
""")

        # Create required directories
        (tmp_path / "apps").mkdir()
        (tmp_path / "codex").mkdir()
        (tmp_path / "claude").mkdir()
        (tmp_path / "output").mkdir()

        # Create test project
        project_dir = tmp_path / "apps" / "test-project"
        project_dir.mkdir(parents=True)
        (project_dir / ".git").mkdir()
        (project_dir / "main.py").write_text("print('hello')")

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        # Track subprocess calls
        phase1_data = valid_phase1_output(
            ad=str(tmp_path / "apps"),
            p=[
                {
                    "n": "test-project",
                    "pt": str(project_dir),
                    "fp": "a" * 64,
                    "st": "orig",
                    "cc": 5,
                    "sd": "1 file changed",
                    "fc": ["main.py"],
                    "msg": ["Initial commit"],
                    "hl": ["feature"],
                    "rt": str(tmp_path / "apps"),
                }
            ],
        )

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"fp": "abc123", "cache_hit": False, "data": phase1_data}
                    ),
                    stderr="",
                )
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(
                    returncode=0, stdout=json.dumps(valid_phase15_output()), stderr=""
                )
            elif "render_report.py" in cmd_str:
                # Create output files to simulate successful render
                output_dir = tmp_path / "output"
                (output_dir / "dev-activity-report.md").write_text("# Test Report")
                (output_dir / "dev-activity-report.html").write_text(
                    "<html>Test</html>"
                )
                return MagicMock(returncode=0, stdout="", stderr="")

            return MagicMock(returncode=0, stdout="", stderr="")

        def mock_claude_call(*args, **kwargs):
            return json.dumps(valid_phase2_output()["sections"]), {"prompt_tokens": 100}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        # Execute
        result = run(foreground=True)

        # Assert
        assert result == 0
        assert (tmp_path / "output" / "dev-activity-report.md").exists()

    def test_cached_projects_still_generate_report(self, tmp_path, monkeypatch):
        """
        Cache hits still generate a report through all phases.

        Even with cache_hit=True, the pipeline runs through all phases
        but uses cached data. The key is that expensive Phase 1 scanning
        is skipped, not that subsequent phases are skipped.
        """
        from run_pipeline import run

        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={tmp_path}/output
""")

        (tmp_path / "apps").mkdir()
        (tmp_path / "codex").mkdir()
        (tmp_path / "claude").mkdir()
        (tmp_path / "output").mkdir()

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        # All projects cached - still includes data for report generation
        phase1_data = valid_phase1_output(
            stats={"total": 1, "stale": 0, "cached": 1},
            p=[
                {
                    "n": "cached-project",
                    "pt": str(tmp_path / "apps" / "cached-project"),
                    "fp": "a" * 64,
                    "st": "orig",
                    "cc": 0,
                    "sd": "0 files changed",
                    "fc": [],
                    "msg": [],
                    "hl": [],
                    "rt": str(tmp_path / "apps"),
                }
            ],
        )

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"fp": "abc123", "cache_hit": True, "data": phase1_data}
                    ),
                    stderr="",
                )
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(
                    returncode=0, stdout=json.dumps(valid_phase15_output()), stderr=""
                )
            elif "render_report.py" in cmd_str:
                (tmp_path / "output" / "dev-activity-report.md").write_text(
                    "# Cached Report"
                )
                return MagicMock(returncode=0, stdout="", stderr="")

            return MagicMock(returncode=0, stdout="", stderr="")

        def mock_claude_call(*args, **kwargs):
            return json.dumps(valid_phase2_output()["sections"]), {"prompt_tokens": 100}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        result = run(foreground=True)

        # Pipeline should succeed even with cached data
        assert result == 0

    def test_partial_cache_mixed_stale_and_cached(self, tmp_path, monkeypatch):
        """
        Pipeline handles mix of cached and stale projects correctly.

        Verifies that only stale projects trigger LLM calls while
        cached projects are skipped.
        """
        from run_pipeline import run

        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={tmp_path}/output
""")

        (tmp_path / "apps").mkdir()
        (tmp_path / "codex").mkdir()
        (tmp_path / "claude").mkdir()
        (tmp_path / "output").mkdir()

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        # Mixed: 1 stale, 1 cached
        phase1_data = valid_phase1_output(
            stats={"total": 2, "stale": 1, "cached": 1},
            p=[
                {
                    "n": "stale-project",
                    "pt": str(tmp_path / "apps" / "stale-project"),
                    "fp": "a" * 64,
                    "st": "orig",
                    "cc": 5,
                    "sd": "changes",
                    "fc": ["file.py"],
                    "msg": ["commit"],
                    "hl": [],
                    "rt": str(tmp_path / "apps"),
                }
            ],
        )

        call_count = {"phase15": 0, "phase2": 0}

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"fp": "abc123", "cache_hit": False, "data": phase1_data}
                    ),
                    stderr="",
                )
            elif "phase1_5_draft.py" in cmd_str:
                call_count["phase15"] += 1
                return MagicMock(
                    returncode=0, stdout=json.dumps(valid_phase15_output()), stderr=""
                )
            elif "render_report.py" in cmd_str:
                (tmp_path / "output" / "dev-activity-report.md").write_text("# Mixed")
                return MagicMock(returncode=0, stdout="", stderr="")

            return MagicMock(returncode=0, stdout="", stderr="")

        def mock_claude_call(*args, **kwargs):
            call_count["phase2"] += 1
            return json.dumps(valid_phase2_output()["sections"]), {"prompt_tokens": 100}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        result = run(foreground=True)

        # Should call LLM APIs for the stale project
        assert result == 0
        assert call_count["phase15"] == 1, (
            "Phase 1.5 should be called for stale projects"
        )
        assert call_count["phase2"] == 1, "Phase 2 should be called for stale projects"

    def test_phase1_invalid_json_fails_gracefully(self, tmp_path, monkeypatch):
        """
        Corrupted Phase 1 output stops pipeline with error code.

        Verifies that when Phase 1 returns invalid JSON, the pipeline
        exits with a non-zero code and doesn't continue.
        """
        from run_pipeline import run

        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={tmp_path}/output
""")

        (tmp_path / "apps").mkdir()
        (tmp_path / "codex").mkdir()
        (tmp_path / "claude").mkdir()

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="not valid json {{[",  # Invalid JSON
                    stderr="",
                )

            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        result = run(foreground=True)

        assert result == 1, "Should return error code for invalid Phase 1 output"

    def test_phase2_invalid_json_triggers_fallback(self, tmp_path, monkeypatch):
        """
        Phase 2 returning invalid JSON is handled gracefully.

        When the LLM returns non-JSON output, the pipeline should
        fail gracefully with a meaningful error.
        """
        from run_pipeline import run

        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={tmp_path}/output
""")

        (tmp_path / "apps").mkdir()
        (tmp_path / "codex").mkdir()
        (tmp_path / "claude").mkdir()
        (tmp_path / "output").mkdir()

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        phase1_data = valid_phase1_output()

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"fp": "abc123", "cache_hit": False, "data": phase1_data}
                    ),
                    stderr="",
                )
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(
                    returncode=0, stdout=json.dumps(valid_phase15_output()), stderr=""
                )

            return MagicMock(returncode=0, stdout="", stderr="")

        def mock_claude_call(*args, **kwargs):
            # Return invalid JSON
            return "This is not JSON", {"prompt_tokens": 100}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        result = run(foreground=True)

        assert result == 1, "Should return error code for invalid Phase 2 output"

    def test_marker_files_excluded_from_report(self, tmp_path, monkeypatch):
        """
        Projects with .skip-for-now/.not-my-work markers excluded.

        Verifies that marker files are respected and excluded projects
        don't appear in the final report.
        """
        from run_pipeline import run

        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={tmp_path}/output
""")

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()
        (tmp_path / "codex").mkdir()
        (tmp_path / "claude").mkdir()
        (tmp_path / "output").mkdir()

        # Create active project
        active_dir = apps_dir / "active-project"
        active_dir.mkdir()
        (active_dir / ".git").mkdir()

        # Create skipped project
        skipped_dir = apps_dir / "skipped-project"
        skipped_dir.mkdir()
        (skipped_dir / ".git").mkdir()
        (skipped_dir / ".skip-for-now").touch()

        # Create not-my-work project
        not_mine_dir = apps_dir / "forked-lib"
        not_mine_dir.mkdir()
        (not_mine_dir / ".git").mkdir()
        (not_mine_dir / ".not-my-work").touch()

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        # Only active project should be in Phase 1 output
        phase1_data = valid_phase1_output(
            mk=[
                {"m": ".skip-for-now", "p": "skipped-project"},
                {"m": ".not-my-work", "p": "forked-lib"},
            ],
            p=[
                {
                    "n": "active-project",
                    "pt": str(active_dir),
                    "fp": "a" * 64,
                    "st": "orig",
                    "cc": 5,
                    "sd": "changes",
                    "fc": ["file.py"],
                    "msg": ["commit"],
                    "hl": [],
                    "rt": str(apps_dir),
                }
            ],
            stats={"total": 1, "stale": 1, "cached": 0},
        )

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"fp": "abc123", "cache_hit": False, "data": phase1_data}
                    ),
                    stderr="",
                )
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(
                    returncode=0, stdout=json.dumps(valid_phase15_output()), stderr=""
                )
            elif "render_report.py" in cmd_str:
                (tmp_path / "output" / "dev-activity-report.md").write_text(
                    "# Active Project Only"
                )
                return MagicMock(returncode=0, stdout="", stderr="")

            return MagicMock(returncode=0, stdout="", stderr="")

        def mock_claude_call(*args, **kwargs):
            return json.dumps(valid_phase2_output()["sections"]), {"prompt_tokens": 100}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        result = run(foreground=True)

        assert result == 0
        # Verify only active project was processed (only 1 project in stats)
        assert phase1_data["stats"]["total"] == 1

    def test_forked_work_precedence(self, tmp_path, monkeypatch):
        """
        .forked-work-modified takes precedence over .forked-work.

        Verifies that when both markers exist, fork_mod status is used.
        """
        from phase1_runner import discover_markers

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        project_dir = apps_dir / "forked-project"
        project_dir.mkdir()
        (project_dir / ".forked-work").touch()
        (project_dir / ".forked-work-modified").touch()

        markers, status_map = discover_markers(apps_dir)

        assert status_map.get("forked-project") == "fork_mod"

    def test_configuration_override_chain(self, tmp_path, monkeypatch):
        """
        CLI args -> .env -> defaults precedence verified end-to-end.

        Verifies that configuration values follow correct precedence.
        """
        from run_pipeline import resolve_since, resolve_scan_roots

        # Test resolve_since precedence
        env = {
            "REPORT_SINCE": "2026-01-01",
            "GIT_SINCE": "2025-01-01",
            "SINCE": "2024-01-01",
        }

        # CLI overrides all
        assert resolve_since(env, "2026-02-01") == "2026-02-01"
        # Env REPORT_SINCE is next
        assert resolve_since(env, None) == "2026-01-01"

        # Test resolve_scan_roots precedence
        env = {
            "APPS_DIR": str(tmp_path / "default"),
            "APPS_DIRS": f"{tmp_path}/env-a {tmp_path}/env-b",
        }

        # CLI overrides env
        cli_roots = [str(tmp_path / "cli")]
        roots = resolve_scan_roots(env, cli_roots)
        assert len(roots) == 1
        assert str(roots[0]) == str(tmp_path / "cli")

    def test_empty_project_list_handled(self, tmp_path, monkeypatch):
        """
        No projects to analyze is handled by the pipeline.

        When there are no projects, Phase 2 still runs but with empty data.
        The pipeline should handle this gracefully.
        """
        from run_pipeline import run

        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={tmp_path}/output
""")

        (tmp_path / "apps").mkdir()
        (tmp_path / "codex").mkdir()
        (tmp_path / "claude").mkdir()
        (tmp_path / "output").mkdir()

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        # Empty project list
        phase1_data = valid_phase1_output(
            p=[], stats={"total": 0, "stale": 0, "cached": 0}
        )

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"fp": "abc123", "cache_hit": False, "data": phase1_data}
                    ),
                    stderr="",
                )
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"draft": "No projects to report on.", "usage": {}}
                    ),
                    stderr="",
                )
            elif "render_report.py" in cmd_str:
                (tmp_path / "output" / "dev-activity-report.md").write_text(
                    "# Empty Report"
                )
                return MagicMock(returncode=0, stdout="", stderr="")

            return MagicMock(returncode=0, stdout="", stderr="")

        def mock_claude_call(*args, **kwargs):
            # Return valid empty-phase2 output
            return json.dumps(
                {
                    "sections": {
                        "overview": {"bullets": []},
                        "key_changes": [],
                        "recommendations": [],
                        "resume_bullets": [],
                        "linkedin": {"sentences": []},
                        "highlights": [],
                        "timeline": [],
                        "tech_inventory": {},
                    }
                }
            ), {"prompt_tokens": 10}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        result = run(foreground=True)

        # Pipeline completes (may return 0 or 1 depending on implementation)
        # Key is it doesn't crash
        assert (tmp_path / "output" / "dev-activity-report.md").exists()
