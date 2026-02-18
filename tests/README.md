# Test Suite for dev-activity-report-skill

A token-efficient, focused test suite covering the most fragile and critical parts of the application.

## Philosophy

- **Integration over isolation**: Tests verify contracts between components, not implementation details
- **Mock external APIs**: All LLM calls are mocked (fast, cheap, deterministic)
- **Target fragility**: Focus on caching, configuration, error handling, and edge cases
- **Minimal maintenance**: Tests are resilient to refactoring; they verify behavior, not structure
- **Schema validation**: JSON schemas enforce contract fidelity for mocks

## Test Structure

### `test_integration_pipeline.py` - Full Pipeline Integration
**Purpose**: End-to-end pipeline tests covering all phases.

- Happy path with output file generation
- Cache hit skips expensive LLM calls
- Mixed stale/cached projects handled correctly
- Invalid JSON fails gracefully
- Marker files exclude projects correctly
- Configuration precedence verified
- Empty project lists handled gracefully

### `test_contracts_and_caching.py` - Contracts & Caching
**Purpose**: JSON schema validation and caching logic.

- Phase 1 output schema validation
- Phase 2 output schema validation
- Fingerprint stability (content-based, not mtime)
- Cache hit/miss logic
- Malformed cache graceful handling

### `test_failure_modes.py` - Aggressive Failure Testing
**Purpose**: Deliberately provoke failures to verify resilience.

- Mtime fragility in non-git projects (PROVOKES FAILURE)
- Editor backup file detection
- Content hash robustness (immune to mtime-only changes)
- Git project robustness (ignores untracked files)
- Corrupted cache files handled gracefully
- Partial JSON handling
- Subprocess crash handling (phase1, claude CLI, render)

### `test_prompt_parsing_and_refresh.py` - Parser + Refresh Coverage
**Purpose**: Verify robust Phase 2 JSON parsing and thorough-refresh planning.

- Phase 2 parser accepts fenced JSON and wrapped output
- Phase 2 parser rejects invalid top-level JSON shapes
- Thorough refresh root resolution behavior
- Thorough refresh marker/cache action planning

### `test_shell_integration.sh` - True E2E Tests
**Purpose**: Actual script execution with real filesystem.

- Phase 1 runner executes successfully
- Marker files correctly excluded
- Cache hit skips rescan
- Fingerprint stability verified
- Configuration precedence verified

## Running the Tests

### All Python Tests
```bash
cd /path/to/dev-activity-report-skill
pytest tests/ -v
```

### With Coverage
```bash
pytest tests/ -v --cov=skills/dev-activity-report-skill/scripts --cov-report=term-missing
```

### Specific Test File
```bash
pytest tests/test_integration_pipeline.py -v
```

### Shell E2E Tests
```bash
./tests/test_shell_integration.sh
```

## JSON Schemas

Schemas in `tests/contracts/` enforce mock fidelity:

- `phase1_output.schema.json` - Phase 1 runner output contract
- `phase2_output.schema.json` - Phase 2 LLM output contract

These ensure mocks match the actual API structures.

## Fixtures

Shared fixtures in `tests/fixtures/__init__.py`:

- `valid_phase1_output()` - Minimal valid Phase 1 data
- `valid_phase15_output()` - Minimal valid Phase 1.5 draft
- `valid_phase2_output()` - Minimal valid Phase 2 data
- `project_with_status(status)` - Project with specific status
- `marker(marker_type, project)` - Marker dict factory

## Test Count

| File | Tests |
|------|-------|
| test_integration_pipeline.py | 10 |
| test_contracts_and_caching.py | 11 |
| test_failure_modes.py | 10 |
| test_prompt_parsing_and_refresh.py | 10 |
| test_shell_integration.sh | 5 |
| **Total** | **~44+** |

## Known Limitations

1. **Git operations**: Tests mock git commands; real git behavior may differ
2. **File system edge cases**: Some edge cases (permissions, symlinks) not fully covered
3. **LLM output variance**: Mocked responses don't capture actual model variability
4. **Schema validation**: Requires `jsonschema` package (tests skip if not installed)
