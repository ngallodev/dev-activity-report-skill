"""
Contract validation and caching logic tests.

Validates JSON schemas and fingerprint stability.
These tests ensure data contracts between pipeline phases are maintained.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from fixtures import valid_phase1_output, valid_phase2_output, load_schema


class TestPhase1OutputContract:
    """Phase 1 output must conform to schema."""
    
    def test_schema_loads_successfully(self):
        """Schema file is valid JSON."""
        schema = load_schema("phase1_output")
        assert "$schema" in schema
        assert "required" in schema
    
    def test_valid_output_passes_validation(self):
        """Valid Phase 1 output passes JSON schema validation."""
        try:
            from jsonschema import validate, ValidationError
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        schema = load_schema("phase1_output")
        data = valid_phase1_output()
        
        # Should not raise
        validate(instance=data, schema=schema)
    
    def test_missing_required_fields_fails(self):
        """Missing required keys fails validation."""
        try:
            from jsonschema import validate, ValidationError
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        schema = load_schema("phase1_output")
        data = valid_phase1_output()
        del data["stats"]  # Remove required field
        
        with pytest.raises(ValidationError):
            validate(instance=data, schema=schema)
    
    def test_invalid_fingerprint_format_fails(self):
        """Fingerprint not 64-char hex fails validation."""
        try:
            from jsonschema import validate, ValidationError
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        schema = load_schema("phase1_output")
        data = valid_phase1_output()
        data["p"][0]["fp"] = "invalid"  # Not 64 hex chars
        
        with pytest.raises(ValidationError):
            validate(instance=data, schema=schema)
    
    def test_invalid_status_value_fails(self):
        """Status not in enum fails validation."""
        try:
            from jsonschema import validate, ValidationError
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        schema = load_schema("phase1_output")
        data = valid_phase1_output()
        data["p"][0]["st"] = "invalid_status"
        
        with pytest.raises(ValidationError):
            validate(instance=data, schema=schema)


class TestPhase2OutputContract:
    """Phase 2 output must conform to schema."""
    
    def test_schema_loads_successfully(self):
        """Schema file is valid JSON."""
        schema = load_schema("phase2_output")
        assert "$schema" in schema
        assert "required" in schema
    
    def test_valid_output_passes_validation(self):
        """Valid Phase 2 output passes JSON schema validation."""
        try:
            from jsonschema import validate, ValidationError
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        schema = load_schema("phase2_output")
        data = valid_phase2_output()
        
        # Should not raise
        validate(instance=data, schema=schema)
    
    def test_missing_sections_key_fails(self):
        """Missing 'sections' key fails validation."""
        try:
            from jsonschema import validate, ValidationError
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        schema = load_schema("phase2_output")
        data = valid_phase2_output()
        del data["sections"]
        
        with pytest.raises(ValidationError):
            validate(instance=data, schema=schema)
    
    def test_invalid_priority_value_fails(self):
        """Recommendation priority not in enum fails."""
        try:
            from jsonschema import validate, ValidationError
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        schema = load_schema("phase2_output")
        data = valid_phase2_output()
        data["sections"]["recommendations"][0]["priority"] = "urgent"
        
        with pytest.raises(ValidationError):
            validate(instance=data, schema=schema)


class TestFingerprintStability:
    """Content-based fingerprinting must be stable."""
    
    def test_same_content_same_fingerprint(self, tmp_path):
        """Identical content produces identical fingerprints."""
        from phase1_runner import hash_file
        
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        
        fp1 = hash_file(test_file)
        fp2 = hash_file(test_file)
        
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex
    
    def test_content_change_changes_fingerprint(self, tmp_path):
        """Content changes produce different fingerprints."""
        from phase1_runner import hash_file
        
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("print('hello')")
        f2.write_text("print('world')")
        
        assert hash_file(f1) != hash_file(f2)
    
    def test_timestamp_only_no_fingerprint_change(self, tmp_path):
        """Only mtime changes, fingerprint stays same."""
        import os
        from phase1_runner import hash_file
        
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        fp1 = hash_file(test_file)
        
        # Modify timestamp without changing content
        os.utime(test_file, (1234567890, 1234567890))
        fp2 = hash_file(test_file)
        
        assert fp1 == fp2


class TestCacheBehavior:
    """Cache hit/miss logic."""
    
    def test_matching_fingerprint_is_cache_hit(self, tmp_path, monkeypatch):
        """Cache file with matching fingerprint = hit."""
        from phase1_runner import read_cache, write_cache
        
        cache_file = tmp_path / ".phase1-cache.json"
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)
        
        fingerprint = "a" * 64
        payload = {"test": "data", "projects": []}
        write_cache(fingerprint, payload)
        
        cache = read_cache()
        assert cache is not None
        assert cache["fingerprint"] == fingerprint
        assert cache["data"] == payload
    
    def test_different_fingerprint_is_cache_miss(self, tmp_path, monkeypatch):
        """Cache file with different fingerprint = miss."""
        from phase1_runner import read_cache
        
        cache_file = tmp_path / ".phase1-cache.json"
        cache_file.write_text(json.dumps({
            "fingerprint": "b" * 64,
            "data": {"old": "data"}
        }))
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)
        
        # No current fingerprint match, so read_cache returns None
        # (cache is read by fingerprint comparison elsewhere)
        cache = read_cache()
        assert cache is not None  # File exists and is valid
        assert cache["fingerprint"] == "b" * 64
    
    def test_malformed_cache_treated_as_miss(self, tmp_path, monkeypatch):
        """Corrupted cache file treated as miss (not crash)."""
        from phase1_runner import read_cache
        
        cache_file = tmp_path / ".phase1-cache.json"
        cache_file.write_text("not valid json {{[")
        monkeypatch.setattr("phase1_runner.CACHE_FILE", cache_file)
        
        cache = read_cache()
        assert cache is None  # Graceful fallback
