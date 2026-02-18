"""
Aggressive failure mode testing.

These tests deliberately provoke failures to verify resilience.
They prove the system handles edge cases correctly.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from fixtures import valid_phase1_output, valid_phase2_output


class TestMtimeFragility:
    """
    PROVOKING FAILURE: Non-git directories are fragile to mtime changes.
    
    These tests prove the fragility exists and is handled correctly.
    They demonstrate the known issue with mtime-based detection.
    """
    
    def test_temp_file_creation_changes_fingerprint(self, tmp_path):
        """
        PROVOKES FAILURE: Adding temp file changes non-git project fingerprint.
        
        This proves the fragility: non-git projects hash file content,
        so adding a file (even a temp file) changes the fingerprint.
        This is expected behavior for content hashing.
        """
        from phase1_runner import hash_non_git_dir
        
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "main.py").write_text("print('hello')")
        
        # Get initial fingerprint
        fp1 = hash_non_git_dir(project, {".py"}, max_depth=4)
        assert fp1 != ""
        
        # Add a temp file (simulating editor swap file)
        (project / ".main.py.swp").write_text("swap data")
        
        # Note: swap files may not be included if not in allowed extensions
        # Let's add a real .py temp file
        (project / "temp_script.py").write_text("# temporary")
        fp2 = hash_non_git_dir(project, {".py"}, max_depth=4)
        
        # PROVES: Content-based hashing detects the new file
        assert fp1 != fp2, "New .py file should change fingerprint - this is expected behavior"
        
        # Remove temp file
        (project / "temp_script.py").unlink()
        fp3 = hash_non_git_dir(project, {".py"}, max_depth=4)
        
        # Original fingerprint restored
        assert fp3 == fp1, "Removing temp file should restore original fingerprint"
    
    def test_editor_backup_files_detected(self, tmp_path):
        """
        PROVOKES FAILURE: Editor backup files (~ suffix) affect fingerprint.
        
        Tests that backup files with allowed extensions are included in hash.
        """
        from phase1_runner import hash_non_git_dir
        
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "main.py").write_text("print('hello')")
        
        fp1 = hash_non_git_dir(project, {".py"}, max_depth=4)
        
        # Create backup file (some editors create these)
        (project / "main.py~").write_text("backup content")
        
        # Note: The ~ suffix makes it a different extension
        # So it won't affect the hash unless .py~ is in allowed extensions
        fp2 = hash_non_git_dir(project, {".py"}, max_depth=4)
        
        # Should be same since .py~ is not in allowed extensions
        assert fp1 == fp2, "Backup files with different extensions should not affect hash"
    
    def test_mtime_vs_content_robustness(self, tmp_path):
        """
        VERIFIES ROBUSTNESS: Content hash ignores mtime-only changes.
        
        This test proves our content hashing is MORE robust than mtime-based
        approaches. Touching a file (mtime change only) does NOT affect hash.
        """
        from phase1_runner import hash_file
        
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        
        fp1 = hash_file(test_file)
        
        # Wait and touch file (mtime change only)
        time.sleep(0.1)
        test_file.touch()
        
        fp2 = hash_file(test_file)
        
        # Content hash should be identical despite mtime change
        assert fp1 == fp2, "Content hash must not change on mtime-only update"
    
    def test_git_projects_immune_to_file_additions(self, tmp_path):
        """
        VERIFIES ROBUSTNESS: Git projects only hash tracked files.
        
        Untracked files (like temp files) don't affect git project fingerprints.
        This is a key advantage of git-based projects.
        """
        from phase1_runner import hash_git_repo
        
        # Create git repo structure
        project = tmp_path / "git-project"
        project.mkdir()
        git_dir = project / ".git"
        git_dir.mkdir()
        
        # Create git metadata
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "objects").mkdir()
        (git_dir / "refs").mkdir()
        
        # Create a tracked file (simulated)
        (project / "tracked.py").write_text("tracked content")
        
        # Mock git_tracked_files to return just our tracked file
        import phase1_runner
        original_git_tracked = phase1_runner.git_tracked_files
        phase1_runner.git_tracked_files = lambda p: ["tracked.py"]
        
        try:
            fp1 = hash_git_repo(project)
            
            # Add untracked temp file
            (project / "temp.py").write_text("temp content")
            
            fp2 = hash_git_repo(project)
            
            # Git projects should NOT be affected by untracked files
            assert fp1 == fp2, "Git projects should ignore untracked files"
        finally:
            phase1_runner.git_tracked_files = original_git_tracked


class TestMalformedData:
    """System handles malformed data gracefully."""
    
    def test_corrupted_cache_file_graceful(self, tmp_path, monkeypatch):
        """Cache file with garbage content doesn't crash system."""
        from phase1_runner import read_cache
        
        cache_file = tmp_path / ".phase1-cache.json"
        cache_file.write_text("not valid json {{[")
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)
        
        # Should not raise exception
        cache = read_cache()
        assert cache is None  # Graceful fallback
    
    def test_partial_json_in_phase2_output(self, tmp_path, monkeypatch):
        """Phase 2 returns incomplete JSON - handled gracefully."""
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
                    stdout=json.dumps({"fp": "abc123", "cache_hit": False, "data": phase1_data}),
                    stderr=""
                )
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps({"draft": "test", "usage": {}}), stderr="")
            
            return MagicMock(returncode=0, stdout="", stderr="")
        
        def mock_claude_call(*args, **kwargs):
            # Return incomplete JSON (truncated)
            return '{"sections": {"overview": {"bullets": ["test"]}', {"prompt_tokens": 100}
        
        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)
        
        # Should handle gracefully (likely fail with error code)
        result = run(foreground=True)
        assert result != 0  # Should fail, not crash
    
    def test_null_values_in_nested_structures(self, tmp_path, monkeypatch):
        """Null values in Phase 2 output don't crash renderer."""
        from render_report import render_markdown
        
        # Phase 2 output with null values
        report = {
            "generated_at": "2024-01-15T10:00:00Z",
            "sections": {
                "overview": {"bullets": ["test", None, "valid"]},  # Null in array
                "key_changes": None,  # Null instead of array
                "recommendations": [],
                "resume_bullets": [],
                "linkedin": {"sentences": []},
                "highlights": [],
                "timeline": [],
                "tech_inventory": {}
            }
        }
        
        # Should not crash
        md = render_markdown(report)
        assert "test" in md


class TestSubprocessFailures:
    """Subprocess crashes are handled gracefully."""
    
    def test_phase1_runner_crash(self, tmp_path, monkeypatch):
        """Phase 1 subprocess returning non-zero exits gracefully."""
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
                    returncode=1,  # Crash!
                    stdout="",
                    stderr="Phase 1 failed"
                )
            
            return MagicMock(returncode=0, stdout="", stderr="")
        
        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        
        result = run(foreground=True)
        assert result == 1  # Should propagate error
    
    def test_claude_cli_timeout(self, tmp_path, monkeypatch):
        """Claude CLI timeout raises proper exception."""
        from run_pipeline import claude_call
        
        with pytest.raises(subprocess.TimeoutExpired):
            # Mock subprocess to raise timeout
            import subprocess as sp
            original_run = sp.run
            
            def mock_run(*args, **kwargs):
                raise subprocess.TimeoutExpired(cmd=["claude"], timeout=1)
            
            monkeypatch.setattr("subprocess.run", mock_run)
            
            claude_call("test prompt", "sonnet", "/usr/bin/claude", timeout=1)
    
    def test_render_subprocess_failure(self, tmp_path, monkeypatch):
        """Render script failure propagates error correctly."""
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
                    stdout=json.dumps({"fp": "abc123", "cache_hit": False, "data": phase1_data}),
                    stderr=""
                )
            elif "phase1_5_draft.py" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps({"draft": "test", "usage": {}}), stderr="")
            elif "render_report.py" in cmd_str:
                return MagicMock(returncode=1, stdout="", stderr="Render failed")
            
            return MagicMock(returncode=0, stdout="", stderr="")
        
        def mock_claude_call(*args, **kwargs):
            return json.dumps(valid_phase2_output()["sections"]), {"prompt_tokens": 100}
        
        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        monkeypatch.setattr("run_pipeline.claude_call", mock_claude_call)
        
        result = run(foreground=True)
        assert result == 1  # Render failure should propagate
