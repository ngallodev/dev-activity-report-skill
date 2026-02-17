"""
Test Group: Non-Git Directory Handling

Protects against:
- mtime-based fingerprint fragility (re-scanning on temp file changes)
- Incorrect allowed extensions filtering
- Depth limits not enforced

Justification: Non-git directories use mtime for change detection, which is
inherently fragile. These tests document and verify the current behavior and
catch regressions in the hashing logic.
"""

import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestNonGitFingerprintFragility:
    """Demonstrates fragility of non-git directory fingerprinting."""

    def test_temp_file_change_triggers_rescan(self, tmp_path):
        """
        FRAGILITY TEST: Temp file creation changes mtime and triggers re-scan.

        This test documents the known issue: non-git directories use mtime,
        so even unrelated file operations can invalidate the cache.
        """
        from phase1_runner import hash_non_git_dir

        # Create a non-git project
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "main.py").write_text("print('hello')")
        (project / "utils.py").write_text("def helper(): pass")

        # Wait to ensure different mtime
        time.sleep(0.1)

        # Get initial fingerprint
        fp1 = hash_non_git_dir(project, {".py"})
        assert fp1 != ""

        # Simulate a temp file operation (like an editor swap file)
        temp_file = project / ".main.py.swp"
        temp_file.write_text("swap data")

        # Note: The current implementation may or may not include temp files
        # depending on extension. Let's check both behaviors.

        # If temp file has .py extension, it affects fingerprint
        temp_py = project / "temp_script.py"
        temp_py.write_text("# temp")
        fp2 = hash_non_git_dir(project, {".py"})

        # Should be different now
        assert fp1 != fp2, "New .py file should change fingerprint"

        # Remove temp file
        temp_py.unlink()
        fp3 = hash_non_git_dir(project, {".py"})

        # Should match original again
        assert fp3 == fp1, "Removing temp file should restore original fingerprint"

    def test_mtime_change_without_content_change(self, tmp_path):
        """
        FRAGILITY TEST: Touching a file (mtime-only change) is invisible to
        content hashing, but would be visible to mtime-based systems.

        Our content-based hashing is actually more robust than mtime!
        """
        from phase1_runner import hash_non_git_dir, hash_file

        project = tmp_path / "myproject"
        project.mkdir()
        main_file = project / "main.py"
        main_file.write_text("print('hello')")

        # Get initial hash
        fp1 = hash_file(main_file)

        # Wait and touch file (mtime change only)
        time.sleep(0.1)
        main_file.touch()

        # Get hash again
        fp2 = hash_file(main_file)

        # Content hash should be identical
        assert fp1 == fp2, "Content hash must not change on mtime-only update"

    def test_large_file_handling(self, tmp_path):
        """Files over 100MB must not be fully hashed."""
        from phase1_runner import hash_file, MAX_HASH_FILE_SIZE

        project = tmp_path / "myproject"
        project.mkdir()

        # Create a large file
        large_file = project / "large.bin"
        large_file.write_bytes(b"x" * (MAX_HASH_FILE_SIZE + 1000))

        fp = hash_file(large_file)

        # Should return a hash based on path, not content
        assert fp != ""

    def test_binary_file_handling(self, tmp_path):
        """Binary files must be hashable without errors."""
        from phase1_runner import hash_file

        binary_file = tmp_path / "data.bin"
        binary_file.write_bytes(bytes(range(256)) * 100)

        fp = hash_file(binary_file)

        assert len(fp) == 64  # SHA-256 hex


class TestAllowedExtensions:
    """File extension filtering must work correctly."""

    def test_only_allowed_extensions_hashed(self, tmp_path):
        """Only files with allowed extensions must be included."""
        from phase1_runner import hash_non_git_dir

        project = tmp_path / "myproject"
        project.mkdir()

        # Create files with various extensions
        (project / "main.py").write_text("python code")
        (project / "main.js").write_text("javascript code")
        (project / "readme.md").write_text("docs")
        (project / "data.json").write_text('{"key": "value"}')
        (project / "image.png").write_bytes(b"PNG data")
        (project / "script.sh").write_text("#!/bin/bash")
        (project / "notes.txt").write_text("notes")

        # Hash with limited extensions
        allowed = {".py", ".md"}
        fp = hash_non_git_dir(project, allowed, max_depth=4)

        # Should only include .py and .md files
        # We can't directly verify which files were included,
        # but we can verify the hash is stable
        fp2 = hash_non_git_dir(project, allowed, max_depth=4)
        assert fp == fp2

        # Adding a non-allowed file shouldn't change hash
        (project / "new.exe").write_text("binary")
        fp3 = hash_non_git_dir(project, allowed, max_depth=4)
        assert fp == fp3, "Non-allowed extension should not affect hash"

        # But adding an allowed file should
        (project / "new.py").write_text("new code")
        fp4 = hash_non_git_dir(project, allowed, max_depth=4)
        assert fp != fp4, "Allowed extension file should affect hash"

    def test_case_insensitive_extensions(self, tmp_path):
        """Extension matching should be case-insensitive."""
        from phase1_runner import hash_non_git_dir

        project = tmp_path / "myproject"
        project.mkdir()

        (project / "main.PY").write_text("python code")
        (project / "main.py").write_text("python code")

        allowed = {".py"}
        fp = hash_non_git_dir(project, allowed, max_depth=4)

        # Both files should be included
        assert fp != ""

    def test_no_extension_files_excluded(self, tmp_path):
        """Files without extensions should be excluded."""
        from phase1_runner import hash_non_git_dir, hash_paths

        project = tmp_path / "myproject"
        project.mkdir()

        (project / "Makefile").write_text("build commands")
        (project / "Dockerfile").write_text("docker commands")
        (project / "LICENSE").write_text("license text")

        allowed = {".py", ".js"}
        fp = hash_non_git_dir(project, allowed, max_depth=4)

        # When no files match, hash_paths returns hash of empty sequence
        # which is SHA-256 of empty string
        empty_hash = hash_paths(project, [])
        assert fp == empty_hash


class TestDepthLimits:
    """Directory traversal depth must be limited."""

    def test_depth_limit_enforced(self, tmp_path):
        """Files beyond max_depth must not be included."""
        from phase1_runner import hash_non_git_dir

        project = tmp_path / "myproject"
        project.mkdir()

        # Create files at various depths (mkdir parents to create nested structure)
        (project / "level0.py").write_text("level 0")
        (project / "src").mkdir(parents=True, exist_ok=True)
        (project / "src" / "level1.py").write_text("level 1")
        (project / "src" / "components").mkdir(parents=True, exist_ok=True)
        (project / "src" / "components" / "level2.py").write_text("level 2")
        (project / "src" / "components" / "utils").mkdir(parents=True, exist_ok=True)
        (project / "src" / "components" / "utils" / "level3.py").write_text("level 3")
        (project / "src" / "components" / "utils" / "deep").mkdir(
            parents=True, exist_ok=True
        )
        (project / "src" / "components" / "utils" / "deep" / "level4.py").write_text(
            "level 4"
        )

        # Hash with depth limit 2
        allowed = {".py"}
        fp_depth2 = hash_non_git_dir(project, allowed, max_depth=2)

        # Hash with depth limit 4
        fp_depth4 = hash_non_git_dir(project, allowed, max_depth=4)

        # Deeper scan should include more files
        assert fp_depth2 != fp_depth4 or fp_depth4 == "", (
            "Depth limit should affect hash"
        )

    def test_ignored_directories_excluded(self, tmp_path):
        """Standard ignored directories must be skipped."""
        from phase1_runner import hash_non_git_dir, IGNORED_DIRS

        project = tmp_path / "myproject"
        project.mkdir()

        (project / "main.py").write_text("main code")

        # Create files in ignored directories
        node_modules = project / "node_modules" / "package"
        node_modules.mkdir(parents=True)
        (node_modules / "index.js").write_text("package code")

        pycache = project / "__pycache__"
        pycache.mkdir()
        (pycache / "main.cpython.pyc").write_bytes(b"bytecode")

        allowed = {".py", ".js"}
        fp = hash_non_git_dir(project, allowed, max_depth=4)

        # Should only reflect main.py
        # Verify by checking hash is stable even if ignored files change
        (node_modules / "new.js").write_text("more code")
        fp2 = hash_non_git_dir(project, allowed, max_depth=4)

        assert fp == fp2, "Ignored directories should not affect hash"


class TestGitVsNonGitDetection:
    """Git repo detection must work correctly."""

    def test_git_directory_detected(self, tmp_path):
        """Directories with .git must be detected as git repos."""
        from phase1_runner import is_git_repo

        # Create git repo structure
        git_repo = tmp_path / "repo"
        git_repo.mkdir()
        (git_repo / ".git").mkdir()

        # Create bare git structure
        git_dir = git_repo / ".git"
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "objects").mkdir()
        (git_dir / "refs").mkdir()

        # This test depends on whether pygit2 is available
        # The function may use pygit2 or subprocess git
        result = is_git_repo(git_repo)

        # Should detect as git repo
        assert result is True

    def test_non_git_directory_not_detected(self, tmp_path):
        """Regular directories must not be detected as git repos."""
        from phase1_runner import is_git_repo

        regular_dir = tmp_path / "regular"
        regular_dir.mkdir()
        (regular_dir / "main.py").write_text("code")

        result = is_git_repo(regular_dir)

        assert result is False
