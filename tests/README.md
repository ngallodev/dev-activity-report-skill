# Compact Test Suite for dev-activity-report-skill

A token-efficient, focused test suite covering the most fragile and critical parts of the application.

## Philosophy

- **Integration over isolation**: Tests verify contracts between components, not implementation details
- **Mock external APIs**: All LLM calls are mocked (fast, cheap, deterministic)
- **Target fragility**: Focus on caching, configuration, error handling, and edge cases
- **Minimal maintenance**: Tests are resilient to refactoring; they verify behavior, not structure

## Test Organization

### `test_caching_integrity.py` - Highest Risk
**What it protects**: The entire pipeline's performance depends on cache correctness.

- **Fingerprint Stability**: Content changes invalidate; timestamps don't
- **Cache Invalidation**: APPS_DIR changes invalidate global cache; file changes invalidate project cache
- **Cache Short-Circuit**: Matching fingerprints skip expensive operations
- **Malformed Cache Handling**: Corrupted cache files don't crash the system

**Why critical**: A single fingerprinting bug causes expensive re-runs and API costs.

### `test_ownership_markers.py`
**What it protects**: Project inclusion/exclusion logic.

- **Marker Detection**: `.skip-for-now`, `.not-my-work`, `.forked-work`, `.forked-work-modified`
- **Depth Limits**: Markers at correct depth are found; deeper ones are ignored
- **Precedence**: `.forked-work-modified` overrides `.forked-work`
- **Cache Hit Detection**: Projects with matching fingerprints are correctly identified

**Why critical**: Marker bugs cause incorrect reports (missing projects or including excluded ones).

### `test_pipeline_contracts.py`
**What it protects**: Inter-phase communication and error handling.

- **Phase 2 JSON Validation**: Invalid JSON or missing fields are detected
- **Subprocess Failures**: phase1_runner crashes, claude CLI timeouts are handled
- **Model Fallback**: Missing API keys trigger deterministic heuristic
- **Render Failures**: Malformed output doesn't crash the renderer

**Why critical**: External dependencies (subprocesses, APIs) fail; the pipeline must degrade gracefully.

### `test_configuration.py`
**What it protects**: Configuration parsing and path handling.

- **Missing/Malformed .env**: Graceful fallbacks to defaults
- **Path Handling**: Tilde expansion, environment variables, relative paths, spaces
- **Output Formats**: `md`, `html`, `md,html` parsing
- **Model Configuration**: Custom models override defaults

**Why critical**: Configuration errors are common user mistakes; clear handling improves UX.

### `test_non_git_handling.py` - Documents Known Fragility
**What it protects**: Non-git directory scanning (inherently fragile).

- **Content-Based Hashing**: More robust than mtime
- **Allowed Extensions**: Only configured extensions are hashed
- **Depth Limits**: Prevents excessive directory traversal
- **Ignored Directories**: `node_modules`, `__pycache__`, etc. are skipped

**Why critical**: Non-git projects use mtime which is fragile; these tests document and verify current behavior.

### `test_render_output.py`
**What it protects**: Final output generation.

- **Markdown/HTML Generation**: Valid output from valid input
- **Empty Sections**: Missing data doesn't crash renderer
- **Special Characters**: Markdown/HTML injection safety
- **File Generation**: Correct output files created

**Why critical**: Render is the final phase; failures here waste all previous LLM calls.

### `test_pipeline_integration.sh`
**What it protects**: Shell-level integration and environment setup.

- **Script Syntax**: All Python files compile
- **Import Checks**: Modules load without errors
- **Environment Handling**: .env file presence/absence
- **Dependencies**: Required and optional packages
- **Marker File Detection**: End-to-end marker detection

**Why critical**: Catches packaging and environment issues pytest might miss.

## Running the Tests

### All Python Tests
```bash
# From project root
cd /lump/apps/dev-activity-report-skill
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=skills/dev-activity-report-skill/scripts --cov-report=term-missing
```

### Specific Test File
```bash
pytest tests/test_caching_integrity.py -v
```

### Shell Integration Tests
```bash
./tests/test_pipeline_integration.sh
```

### Quick Smoke Test
```bash
# Fastest test - just syntax and imports
python3 -c "import sys; sys.path.insert(0, 'skills/dev-activity-report-skill/scripts'); import phase1_runner, phase1_5_draft, run_pipeline, render_report; print('All imports OK')"
```

## Test Fixtures

Tests use pytest's `tmp_path` and `monkeypatch` fixtures extensively:

- **Temporary directories**: Each test gets a clean filesystem
- **Mocked subprocess**: No actual git/LLM calls
- **Mocked environment**: Isolated .env files per test
- **Deterministic**: Same inputs always produce same outputs

## Adding New Tests

When adding tests, follow these principles:

1. **Target fragility**: What could break and cause the most pain?
2. **Mock externals**: Never call real LLM APIs or subprocesses
3. **Test contracts**: Input/output behavior, not implementation
4. **Document intent**: Explain WHY the test matters in the docstring
5. **Keep it fast**: Tests should complete in milliseconds

Example:
```python
def test_cache_shortcircuit_skips_rescan(tmp_path, monkeypatch):
    """
    Cache hit must skip the expensive Haiku scan.
    
    This protects against API cost overruns. If the fingerprint
    matches, we must reuse the cached payload verbatim.
    """
    # Setup...
    # Assert cache hit triggers short-circuit...
```

## Continuous Integration

For CI/CD integration:

```yaml
# Example GitHub Actions
- name: Run Tests
  run: |
    pip install pytest
    pytest tests/ -v --tb=short
    
- name: Run Shell Tests
  run: |
    chmod +x tests/test_pipeline_integration.sh
    ./tests/test_pipeline_integration.sh
```

## Known Limitations

1. **Git operations**: Tests mock git commands; real git behavior may differ
2. **File system edge cases**: Some edge cases (permissions, symlinks) not fully covered
3. **Platform differences**: Primarily tested on Linux/macOS
4. **LLM output variance**: Mocked responses don't capture actual model variability

## Maintenance

- **When to update**: When bugs are found in production, add regression tests
- **When to delete**: Tests that no longer match the contract (not implementation changes)
- **Review cadence**: Quarterly review for test relevance
