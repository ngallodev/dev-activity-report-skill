"""
Test Group: Ownership & Marker File Logic

Protects against:
- Projects being included when they should be skipped
- Marker files not being detected at correct depth
- Forked-work-modified logic failing

Justification: Marker files control project inclusion/exclusion. A bug here
causes incorrect reports (including skipped projects or missing fork info).
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestMarkerDetection:
    """Marker files must be detected and respected."""

    def test_skip_marker_omits_project(self, tmp_path):
        """Projects with .skip-for-now must be excluded from output."""
        from phase1_runner import discover_markers, collect_projects

        # Create project structure
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        active_project = apps_dir / "active-proj"
        active_project.mkdir()
        (active_project / ".git").mkdir()
        (active_project / "main.py").write_text("code")

        skipped_project = apps_dir / "skipped-proj"
        skipped_project.mkdir()
        (skipped_project / ".git").mkdir()
        (skipped_project / ".skip-for-now").write_text("")
        (skipped_project / "main.py").write_text("code")

        # Discover markers
        markers, status_map = discover_markers(apps_dir)

        # Check status map
        assert status_map.get("skipped-proj") == "skip"
        assert "active-proj" not in status_map

    def test_not_my_work_excludes_project(self, tmp_path):
        """Projects with .not-my-work must be excluded."""
        from phase1_runner import discover_markers

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        not_mine = apps_dir / "forked-lib"
        not_mine.mkdir()
        (not_mine / ".not-my-work").write_text("")

        markers, status_map = discover_markers(apps_dir)

        assert status_map.get("forked-lib") == "not"

    def test_forked_work_detected(self, tmp_path):
        """Projects with .forked-work must be marked as fork."""
        from phase1_runner import discover_markers

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        forked = apps_dir / "forked-proj"
        forked.mkdir()
        (forked / ".forked-work").write_text("")

        markers, status_map = discover_markers(apps_dir)

        assert status_map.get("forked-proj") == "fork"

    def test_forked_work_modified_takes_precedence(self, tmp_path):
        """.forked-work-modified must override .forked-work."""
        from phase1_runner import discover_markers

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        forked = apps_dir / "forked-proj"
        forked.mkdir()
        (forked / ".forked-work").write_text("")
        (forked / ".forked-work-modified").write_text("")

        markers, status_map = discover_markers(apps_dir)

        # .forked-work-modified takes precedence
        assert status_map.get("forked-proj") == "fork_mod"

    def test_marker_at_depth_2_found(self, tmp_path):
        """Markers at depth 2 (project subdirectory) must be detected."""
        from phase1_runner import discover_markers

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Project with nested structure
        project = apps_dir / "myproject"
        project.mkdir()
        subdir = project / "backend"
        subdir.mkdir()
        (subdir / ".skip-for-now").write_text("")

        markers, status_map = discover_markers(apps_dir)

        # Should still find the marker at depth 2
        assert status_map.get("myproject") == "skip"

    def test_marker_beyond_depth_2_ignored(self, tmp_path):
        """Markers beyond depth 2 must be ignored."""
        from phase1_runner import discover_markers

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Project with deeply nested structure
        project = apps_dir / "myproject"
        project.mkdir()
        deep = project / "src" / "components" / "utils"
        deep.mkdir(parents=True)
        (deep / ".skip-for-now").write_text("")

        markers, status_map = discover_markers(apps_dir)

        # Should NOT find marker beyond depth 2
        assert "myproject" not in status_map


class TestProjectCollection:
    """Project collection must respect marker-based filtering."""

    def test_only_active_projects_included(self, tmp_path):
        """collect_projects must exclude skipped/not-my-work projects."""
        from phase1_runner import discover_markers, collect_projects

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Active project
        active = apps_dir / "active"
        active.mkdir()
        (active / ".git").mkdir()
        (active / "main.py").write_text("code")

        # Skipped project
        skipped = apps_dir / "skipped"
        skipped.mkdir()
        (skipped / ".skip-for-now").write_text("")
        (skipped / ".git").mkdir()

        markers, status_map = discover_markers(apps_dir)
        projects = collect_projects(apps_dir, status_map, {".py"})

        project_names = {p["name"] for p in projects}
        assert "active" in project_names
        assert "skipped" not in project_names

    def test_nonexistent_apps_dir_handled(self, tmp_path):
        """Non-existent APPS_DIR must return empty project list."""
        from phase1_runner import discover_markers, collect_projects

        nonexistent = tmp_path / "does-not-exist"
        markers, status_map = discover_markers(nonexistent)
        projects = collect_projects(nonexistent, status_map, {".py"})

        assert markers == []
        assert status_map == {}
        assert projects == []

    def test_file_not_directory_ignored(self, tmp_path):
        """Files in apps_dir (not directories) must be ignored."""
        from phase1_runner import discover_markers, collect_projects

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()
        (apps_dir / "not-a-project.txt").write_text("oops")

        markers, status_map = discover_markers(apps_dir)
        projects = collect_projects(apps_dir, status_map, {".py"})

        assert projects == []


class TestCacheHitDetection:
    """Cache hit detection must work with project fingerprints."""

    def test_cache_hit_when_fingerprint_matches(self, tmp_path, monkeypatch):
        """Project with matching fingerprint must have cache_hit=True."""
        from phase1_runner import collect_projects, discover_markers, hash_non_git_dir

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        project = apps_dir / "myproject"
        project.mkdir()
        (project / "main.py").write_text("code")

        # Use non-git directory hashing (mocking git is complex)
        # Get actual fingerprint
        fingerprint = hash_non_git_dir(project, {".py"})

        # Create cache file with matching fingerprint
        cache_file = project / ".dev-report-cache.md"
        cache_file.write_text(f"fingerprint: {fingerprint}\n")

        # Mock is_git_repo to return False so we use non-git hashing
        monkeypatch.setattr("phase1_runner.is_git_repo", lambda p: False)

        markers, status_map = discover_markers(apps_dir)
        projects = collect_projects(apps_dir, status_map, {".py"})

        assert len(projects) == 1
        assert projects[0]["cache_hit"] is True
        assert projects[0]["cached_fp"] == fingerprint

    def test_cache_miss_when_fingerprint_differs(self, tmp_path):
        """Project with different fingerprint must have cache_hit=False."""
        from phase1_runner import collect_projects, discover_markers

        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        project = apps_dir / "myproject"
        project.mkdir()
        (project / ".git").mkdir()
        (project / "main.py").write_text("code")

        # Create cache file with wrong fingerprint
        cache_file = project / ".dev-report-cache.md"
        cache_file.write_text("fingerprint: " + "0" * 64 + "\n")

        markers, status_map = discover_markers(apps_dir)
        projects = collect_projects(apps_dir, status_map, {".py"})

        assert len(projects) == 1
        assert projects[0]["cache_hit"] is False
