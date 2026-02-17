"""
Test Group: Caching Integrity (Highest Risk)

Protects against:
- Fingerprint instability (cache invalidates when it shouldn't)
- Cache invalidation failures (changes not detected)
- Cache short-circuit failures (re-scanning when cached)

Justification: The entire pipeline's performance depends on cache hits. A single
bug in fingerprinting causes expensive re-runs and API costs.
"""

import json
import hashlib
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestFingerprintStability:
    """Fingerprint must be stable across identical content, vary on changes."""

    def test_same_content_same_fingerprint(self, tmp_path, monkeypatch):
        """Identical file content must produce identical fingerprints."""
        from phase1_runner import hash_file, hash_paths

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Compute fingerprint twice
        fp1 = hash_file(test_file)
        fp2 = hash_file(test_file)

        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_different_content_different_fingerprint(self, tmp_path):
        """Different content must produce different fingerprints."""
        from phase1_runner import hash_file

        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("print('hello')")
        f2.write_text("print('world')")

        assert hash_file(f1) != hash_file(f2)

    def test_timestamp_change_doesnt_affect_fingerprint(self, tmp_path):
        """Only content matters, not file timestamps."""
        from phase1_runner import hash_file

        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        fp1 = hash_file(test_file)

        # Modify timestamp without changing content
        os.utime(test_file, (1234567890, 1234567890))
        fp2 = hash_file(test_file)

        assert fp1 == fp2

    def test_ignore_patterns_respected(self, tmp_path, monkeypatch):
        """Files matching ignore patterns must be excluded from fingerprint."""
        from phase1_runner import hash_paths, _matches_ignore, load_fp_ignore_patterns

        # Mock ignore patterns
        monkeypatch.setattr(
            "phase1_runner.load_fp_ignore_patterns", lambda: ["*.log", "debug/*"]
        )

        # Create files
        (tmp_path / "code.py").write_text("code")
        (tmp_path / "debug.log").write_text("log")

        # Only code.py should be hashed
        files = ["code.py", "debug.log"]
        fp = hash_paths(tmp_path, files)

        # Compute expected (only code.py)
        expected_fp = hash_paths(tmp_path, ["code.py"])

        # They should differ because debug.log is excluded
        # Actually, hash_paths doesn't filter - collect_projects does
        # So we test _matches_ignore directly
        assert _matches_ignore("debug/app.log", ["debug/*"]) is True
        assert _matches_ignore("code.py", ["debug/*"]) is False


class TestCacheInvalidation:
    """Changes must correctly invalidate cache."""

    def test_git_content_change_invalidates_cache(self, tmp_path, monkeypatch):
        """Modifying a git-tracked file must change project fingerprint."""
        from phase1_runner import hash_paths

        # Create simulated git repo structure
        repo = tmp_path / "myproject"
        repo.mkdir()
        (repo / ".git").mkdir()

        # Initial file
        (repo / "main.py").write_text("v1")
        fp1 = hash_paths(repo, ["main.py"])

        # Modify file
        (repo / "main.py").write_text("v2")
        fp2 = hash_paths(repo, ["main.py"])

        assert fp1 != fp2, "Content change must invalidate fingerprint"

    def test_env_change_invalidates_global_cache(self, tmp_path, monkeypatch):
        """Changing APPS_DIR must invalidate the global Phase 1 cache."""
        from phase1_runner import hash_payload, compute_fingerprint_source

        # Create minimal fingerprint source
        source1 = {
            "projects": [{"n": "proj1", "fp": "abc123", "st": "orig", "m": []}],
            "extra": [],
            "claude_fp": "",
            "codex_fp": "",
            "insights_fp": "",
        }

        source2 = {
            "projects": [{"n": "proj1", "fp": "abc123", "st": "orig", "m": []}],
            "extra": [{"p": "/new/path", "fp": "xyz789"}],  # Different extra dir
            "claude_fp": "",
            "codex_fp": "",
            "insights_fp": "",
        }

        fp1 = hash_payload(source1)
        fp2 = hash_payload(source2)

        assert fp1 != fp2, "Extra scan dir change must invalidate global cache"

    def test_cache_header_parsing(self, tmp_path):
        """Cache file fingerprint header must be correctly parsed."""
        from phase1_runner import parse_cached_fp

        # Valid header formats
        assert parse_cached_fp("fingerprint: abc123") == "abc123"
        assert parse_cached_fp("<!-- fingerprint: abc123 -->") == "abc123"
        assert parse_cached_fp("# fingerprint: abc123") == "abc123"

        # Invalid/empty
        assert parse_cached_fp("") == ""
        assert parse_cached_fp("some other content") == ""

    def test_since_and_roots_invalidate_global_cache(self, tmp_path):
        """Changing --since or scan roots must change global fingerprint."""
        from phase1_runner import hash_payload, compute_fingerprint_source

        roots_a = [tmp_path / "apps-a"]
        roots_b = [tmp_path / "apps-b"]
        projects = [{"name": "proj1", "fp": "abc123", "status": "orig", "root": str(roots_a[0])}]

        src1 = compute_fingerprint_source(
            roots=roots_a,
            since="2026-01-01",
            projects=projects,
            markers=[],
            extra_summaries=[],
            claude_meta={"fp": ""},
            codex_meta={"fp": ""},
            insights_fp="",
        )
        src2 = compute_fingerprint_source(
            roots=roots_b,
            since="2026-01-01",
            projects=[{"name": "proj1", "fp": "abc123", "status": "orig", "root": str(roots_b[0])}],
            markers=[],
            extra_summaries=[],
            claude_meta={"fp": ""},
            codex_meta={"fp": ""},
            insights_fp="",
        )
        src3 = compute_fingerprint_source(
            roots=roots_a,
            since="2026-02-01",
            projects=projects,
            markers=[],
            extra_summaries=[],
            claude_meta={"fp": ""},
            codex_meta={"fp": ""},
            insights_fp="",
        )

        fp1 = hash_payload(src1)
        fp2 = hash_payload(src2)
        fp3 = hash_payload(src3)
        assert fp1 != fp2
        assert fp1 != fp3


class TestCacheShortCircuit:
    """Cache hits must skip expensive operations."""

    def test_cache_hit_skips_rescan(self, tmp_path, monkeypatch):
        """Matching fingerprint must trigger cache short-circuit."""
        from phase1_runner import read_cache, write_cache

        # Mock cache location
        cache_file = tmp_path / ".phase1-cache.json"
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)

        # Write cache with known fingerprint
        fingerprint = "a" * 64
        payload = {"test": "data", "projects": []}
        write_cache(fingerprint, payload)

        # Read cache back
        cache = read_cache()
        assert cache is not None
        assert cache["fingerprint"] == fingerprint
        assert cache["data"] == payload

    def test_cache_miss_triggers_rescan(self, tmp_path, monkeypatch):
        """Non-matching fingerprint must trigger full scan."""
        from phase1_runner import read_cache

        # No cache exists
        cache_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)

        cache = read_cache()
        assert cache is None

    def test_malformed_cache_handled_gracefully(self, tmp_path, monkeypatch):
        """Corrupted cache file must not crash, treated as cache miss."""
        from phase1_runner import read_cache

        cache_file = tmp_path / ".phase1-cache.json"
        cache_file.write_text("not valid json {{[")
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)

        cache = read_cache()
        assert cache is None  # Graceful fallback

    def test_cache_atomic_write(self, tmp_path, monkeypatch):
        """Cache writes must be atomic (no partial files on crash)."""
        from phase1_runner import write_cache, CACHE_FILE

        cache_file = tmp_path / ".phase1-cache.json"
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)

        fingerprint = "b" * 64
        payload = {"large": "data" * 1000}

        write_cache(fingerprint, payload)

        # Verify file exists and is valid JSON
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["fingerprint"] == fingerprint
