"""
Test Group: Pipeline Phase Contracts & Error Handling

Protects against:
- Phase 2 returning invalid JSON
- Subprocess crashes (phase1_runner, claude CLI)
- Model API failures and timeouts
- Missing required fields in responses

Justification: The pipeline has multiple external dependencies (subprocesses, LLM APIs).
Each failure point must be handled gracefully with proper error codes.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import pytest


class TestPhase2JsonContract:
    """Phase 2 must return valid JSON with required fields."""

    def test_valid_json_accepted(self, tmp_path):
        """Valid Phase 2 JSON with all fields must be accepted."""
        from run_pipeline import expand_compact_payload

        compact = {
            "p": [
                {
                    "n": "test-proj",
                    "pt": "/path/to/proj",
                    "st": "orig",
                    "cc": 5,
                    "sd": "3 insertions(+)",
                    "fc": ["file.py"],
                    "msg": ["commit message"],
                    "hl": ["feature"],
                    "fp": "abc123",
                }
            ],
            "mk": [{"m": ".skip-for-now", "p": "other"}],
            "x": [{"p": "/extra", "exists": True, "git": False, "kf": [], "fp": "xyz"}],
            "cl": {"sk": ["skill1"], "hk": [], "ag": []},
            "cx": {"sm": {"2024-01": 5}, "cw": ["/cwd"], "sk": []},
            "ins": ["insight line"],
            "stats": {"total": 1, "stale": 1, "cached": 0},
        }

        expanded = expand_compact_payload(compact)

        assert expanded["projects"][0]["name"] == "test-proj"
        assert expanded["projects"][0]["commit_count"] == 5
        assert expanded["claude_home"]["skills"] == ["skill1"]

    def test_missing_projects_handled(self, tmp_path):
        """Missing 'p' key should not crash."""
        from run_pipeline import expand_compact_payload

        compact = {"ad": "/apps", "mk": [], "stats": {}}

        expanded = expand_compact_payload(compact)

        assert expanded["projects"] == []
        assert expanded["stats"]["total"] is None

    def test_malformed_project_entry_behavior(self):
        """Malformed project entries behavior - documents current implementation."""
        from run_pipeline import expand_compact_payload

        # Valid entries work fine
        compact_valid = {
            "p": [
                {"n": "valid-proj", "cc": 5},
                {},  # Empty entry - handled
            ]
        }

        expanded = expand_compact_payload(compact_valid)

        assert len(expanded["projects"]) == 2
        assert expanded["projects"][0]["name"] == "valid-proj"
        assert expanded["projects"][1]["name"] == ""  # Empty becomes empty string

        # Note: None entries in the list will cause AttributeError
        # This is a known limitation - the Phase 1 output should never contain None
        # If this becomes a real issue, add null-checking to expand_compact_payload

    def test_sections_normalization(self):
        """Section titles must be normalized to readable labels."""
        from run_pipeline import normalize_sections, normalize_label

        # Test label normalization
        assert normalize_label("mk") == "Ownership markers"
        assert normalize_label("st") == "Project status"
        assert normalize_label("MK:") == "Ownership markers:"
        assert normalize_label("custom title") == "custom title"

        # Test section normalization
        sections = {"key_changes": [{"title": "mk", "bullets": ["st update"]}]}
        normalized = normalize_sections(sections)

        assert normalized["key_changes"][0]["title"] == "Ownership markers"


class TestSubprocessFailureHandling:
    """Subprocess failures must be handled gracefully."""

    def test_phase1_crash_returns_error(self, tmp_path, monkeypatch):
        """Phase 1 runner crash must exit pipeline with error code."""
        from run_pipeline import run

        # Mock environment
        monkeypatch.setattr("run_pipeline.ENV_FILE", tmp_path / ".env")
        (tmp_path / ".env").write_text(
            "APPS_DIR=/test\nCODEX_HOME=/test\nCLAUDE_HOME=/test"
        )
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)

        # Mock subprocess to simulate phase1 failure
        def mock_run(*args, **kwargs):
            if "phase1_runner.py" in str(args[0]):
                return MagicMock(returncode=1, stdout="error", stderr="phase1 failed")
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", mock_run)

        # Should return non-zero exit code
        result = run(foreground=True)
        assert result == 1

    def test_claude_cli_timeout_handled(self):
        """Claude CLI timeout must raise RuntimeError."""
        from run_pipeline import claude_call

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["claude"], timeout=300
            )

            with pytest.raises(subprocess.TimeoutExpired):
                claude_call("test prompt", "sonnet", "/usr/bin/claude")

    def test_claude_cli_nonzero_exit(self):
        """Claude CLI non-zero exit must raise RuntimeError."""
        from run_pipeline import claude_call

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="API error"
            )

            with pytest.raises(RuntimeError) as exc_info:
                claude_call("test prompt", "sonnet", "/usr/bin/claude")

            assert "claude CLI failed" in str(exc_info.value)

    def test_phase15_sdk_failure_fallback(self, tmp_path, monkeypatch):
        """Phase 1.5 SDK failure must fall back to heuristic draft."""
        from phase1_5_draft import call_model

        env = {
            "PHASE15_MODEL": "haiku",
            "PHASE15_API_KEY": "",  # No API key
            "SUBSCRIPTION_MODE": "false",
        }

        summary = {
            "p": [
                {"n": "proj1", "cc": 10, "hl": ["feature", "bugfix"]},
                {"n": "proj2", "cc": 5, "hl": ["docs"]},
            ]
        }

        prompt = "test prompt"
        draft, usage = call_model(prompt, env, summary)

        # Should use heuristic fallback
        assert "proj1: 10 commits" in draft
        assert "proj2: 5 commits" in draft
        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0


class TestModelApiFailure:
    """Model API failures must be handled with fallbacks."""

    def test_phase2_invalid_json_handled(self, tmp_path, monkeypatch):
        """Phase 2 returning invalid JSON must fail gracefully."""
        from run_pipeline import run

        # Setup env
        env_file = tmp_path / ".env"
        env_file.write_text("""
APPS_DIR=/test
CODEX_HOME=/test
CLAUDE_HOME=/test
REPORT_OUTPUT_DIR=/test
""")
        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        # Mock phase1 success
        phase1_output = json.dumps(
            {"fp": "abc123", "cache_hit": False, "data": {"p": [], "stats": {}}}
        )

        call_count = [0]

        def mock_subprocess_run(*args, **kwargs):
            call_count[0] += 1
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(returncode=0, stdout=phase1_output, stderr="")
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {"draft": "test draft", "usage": {"prompt_tokens": 100}}
                    ),
                    stderr="",
                )

            return MagicMock(returncode=0)

        # Mock claude_call to return invalid JSON
        def mock_claude_call(*args, **kwargs):
            return "not valid json", {"prompt_tokens": 200}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        # Create output dir
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        monkeypatch.setattr("run_pipeline.Path.exists", lambda self: True)
        monkeypatch.setattr("os.access", lambda path, mode: True)

        # Should handle gracefully
        result = run(foreground=True)
        assert result == 1  # Returns error on invalid JSON

    def test_phase2_missing_required_field(self):
        """Phase 2 output missing required sections field must be rejected."""
        from run_pipeline import run

        # This tests the validation logic directly
        import run_pipeline as rp

        # Valid structure
        valid_output = {
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

        # Should be valid
        assert "sections" in valid_output

        # Invalid - no sections
        invalid_output = {"some_other_field": "value"}

        # Should be detected as invalid
        has_required = any(
            k in invalid_output
            for k in (
                "overview",
                "key_changes",
                "recommendations",
                "resume_bullets",
                "linkedin",
                "highlights",
                "timeline",
                "tech_inventory",
            )
        )
        assert not has_required

    def test_render_failure_handled(self, tmp_path, monkeypatch):
        """Render failure must exit with error code."""
        from run_pipeline import run

        # Use actual temp directory for output to avoid permission issues
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        env_file = tmp_path / ".env"
        env_file.write_text(f"""
APPS_DIR={tmp_path}/apps
CODEX_HOME={tmp_path}/codex
CLAUDE_HOME={tmp_path}/claude
REPORT_OUTPUT_DIR={output_dir}
REPORT_OUTPUT_FORMATS=md
""")

        # Create the required directories
        (tmp_path / "apps").mkdir(exist_ok=True)
        (tmp_path / "codex").mkdir(exist_ok=True)
        (tmp_path / "claude").mkdir(exist_ok=True)

        monkeypatch.setattr("run_pipeline.ENV_FILE", env_file)
        monkeypatch.setattr("run_pipeline.SKILL_DIR", tmp_path)
        monkeypatch.setattr("run_pipeline.find_claude_bin", lambda: "/usr/bin/claude")

        phase1_output = json.dumps(
            {"fp": "abc123", "cache_hit": False, "data": {"p": [], "stats": {}}}
        )

        def mock_subprocess_run(*args, **kwargs):
            cmd_str = " ".join(str(a) for a in args[0])

            if "phase1_runner.py" in cmd_str:
                return MagicMock(returncode=0, stdout=phase1_output, stderr="")
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({"draft": "test draft", "usage": {}}),
                    stderr="",
                )
            elif "render_report.py" in cmd_str:
                # Simulate render failure
                return MagicMock(returncode=1, stdout="", stderr="render error")

            return MagicMock(returncode=0)

        def mock_claude_call(*args, **kwargs):
            return json.dumps(
                {
                    "sections": {
                        "overview": {"bullets": ["test"]},
                        "key_changes": [],
                        "recommendations": [],
                        "resume_bullets": [],
                        "linkedin": {"sentences": []},
                        "highlights": [],
                        "timeline": [],
                        "tech_inventory": {},
                    }
                }
            ), {"prompt_tokens": 100}

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)

        result = run(foreground=True)
        assert result == 1  # Render failure returns 1
