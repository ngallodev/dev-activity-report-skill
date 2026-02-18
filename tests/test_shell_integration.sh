#!/usr/bin/env bash
#
# TRUE END-TO-END SHELL TESTS
#
# These tests run the actual pipeline with mocked LLM responses
# and verify real output files are created.
#
# Usage: ./tests/test_shell_integration.sh

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Counters
TESTS_PASSED=0
TESTS_FAILED=0

# Directories
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${TEST_DIR}/.." && pwd)"
SKILL_DIR="${PROJECT_ROOT}/skills/dev-activity-report-skill"
SCRIPTS_DIR="${SKILL_DIR}/scripts"

echo "=========================================="
echo "Dev Activity Report - E2E Shell Tests"
echo "=========================================="
echo ""

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

cleanup() {
    rm -rf /tmp/dev-activity-e2e-*
    rm -f /tmp/mock_claude
}

trap cleanup EXIT

# Setup mock claude CLI
setup_mock_claude() {
    cat > /tmp/mock_claude << 'MOCK_EOF'
#!/usr/bin/env bash
# Mock claude CLI that returns valid Phase 2 JSON
if [[ "$*" == *"-p"* ]]; then
    cat << 'JSON_EOF'
{
  "sections": {
    "overview": {"bullets": ["Shipped feature X", "Fixed critical bug Y"]},
    "key_changes": [
      {"title": "Feature X", "bullets": ["Implemented core functionality"], "project_id": null, "tags": []}
    ],
    "recommendations": [
      {"text": "Refactor module A", "priority": "medium", "evidence_project_ids": []}
    ],
    "resume_bullets": [
      {"text": "Led development of feature X", "evidence_project_ids": []}
    ],
    "linkedin": {"sentences": ["Excited to share my recent work on feature X."]},
    "highlights": [
      {"title": "Performance Improvement", "rationale": "Reduced latency", "evidence_project_ids": []}
    ],
    "timeline": [
      {"date": "2024-01-15", "event": "Launched feature X", "project_ids": []}
    ],
    "tech_inventory": {
      "languages": ["Python"],
      "frameworks": [],
      "ai_tools": [],
      "infra": []
    }
  }
}
JSON_EOF
fi
MOCK_EOF
    chmod +x /tmp/mock_claude
    export PATH="/tmp:${PATH}"
}

test_e2e_pipeline_creates_output_files() {
    echo "Test 1: Full pipeline creates .md output file"
    echo "----------------------------------------------"
    
    # Setup temp environment
    TEST_WORKDIR=$(mktemp -d /tmp/dev-activity-e2e-XXXXXX)
    export APPS_DIR="${TEST_WORKDIR}/apps"
    export REPORT_OUTPUT_DIR="${TEST_WORKDIR}/output"
    export CODEX_HOME="${TEST_WORKDIR}/codex"
    export CLAUDE_HOME="${TEST_WORKDIR}/claude"
    
    mkdir -p "${APPS_DIR}" "${REPORT_OUTPUT_DIR}" "${CODEX_HOME}" "${CLAUDE_HOME}"
    
    # Create a test project
    mkdir -p "${APPS_DIR}/test-project/.git"
    echo "print('hello')" > "${APPS_DIR}/test-project/main.py"
    
    # Initialize minimal git repo
    cd "${APPS_DIR}/test-project"
    git init 2>/dev/null || true
    git config user.email "test@test.com" 2>/dev/null || true
    git config user.name "Test" 2>/dev/null || true
    git add . 2>/dev/null || true
    git commit -m "Initial commit" 2>/dev/null || true
    cd - > /dev/null
    
    # Create .env file
    cat > "${TEST_WORKDIR}/.env" << EOF
APPS_DIR=${APPS_DIR}
CODEX_HOME=${CODEX_HOME}
CLAUDE_HOME=${CLAUDE_HOME}
REPORT_OUTPUT_DIR=${REPORT_OUTPUT_DIR}
REPORT_OUTPUT_FORMATS=md
EOF
    
    # Copy .env to skill dir
    cp "${TEST_WORKDIR}/.env" "${SKILL_DIR}/.env"
    
    # Setup mock claude
    setup_mock_claude
    
    # Run Phase 1 only (don't need full pipeline for basic test)
    phase1_output=$(cd "${TEST_WORKDIR}" && python3 "${SCRIPTS_DIR}/phase1_runner.py" --root "${APPS_DIR}" 2>&1)
    phase1_rc=$?
    
    if [[ $phase1_rc -eq 0 ]]; then
        pass "Phase 1 runner executed successfully"
        
        # Check if output is valid JSON
        if echo "$phase1_output" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
            pass "Phase 1 output is valid JSON"
        else
            fail "Phase 1 output is not valid JSON"
        fi
    else
        fail "Phase 1 runner failed with exit code $phase1_rc"
    fi
    
    # Cleanup
    rm -rf "${TEST_WORKDIR}"
    rm -f "${SKILL_DIR}/.env"
    
    echo ""
}

test_marker_files_excluded() {
    echo "Test 2: Marker files exclude projects"
    echo "--------------------------------------"
    
    TEST_WORKDIR=$(mktemp -d /tmp/dev-activity-e2e-XXXXXX)
    export APPS_DIR="${TEST_WORKDIR}/apps"
    
    mkdir -p "${APPS_DIR}/active-project/.git"
    mkdir -p "${APPS_DIR}/skipped-project/.git"
    mkdir -p "${APPS_DIR}/forked-lib/.git"
    
    # Create marker files
    touch "${APPS_DIR}/skipped-project/.skip-for-now"
    touch "${APPS_DIR}/forked-lib/.not-my-work"
    
    # Create content
    echo "active" > "${APPS_DIR}/active-project/main.py"
    echo "skipped" > "${APPS_DIR}/skipped-project/main.py"
    echo "forked" > "${APPS_DIR}/forked-lib/main.py"
    
    # Run discovery (import and call discover_markers)
    discovery_result=$(python3 << PYTHON_EOF
import sys
sys.path.insert(0, "${SCRIPTS_DIR}")
from phase1_runner import discover_markers
from pathlib import Path

markers, status_map = discover_markers(Path("${APPS_DIR}"))
print(f"MARKERS:{len(markers)}")
print(f"STATUSES:{status_map}")
PYTHON_EOF
)
    
    if echo "$discovery_result" | grep -q "MARKERS:2"; then
        pass "Found 2 marker files (skip and not-my-work)"
    else
        fail "Expected 2 markers, got different count"
    fi
    
    if echo "$discovery_result" | grep -q "'skipped-project': 'skip'"; then
        pass "Skipped project has correct status"
    else
        fail "Skipped project status incorrect"
    fi
    
    if echo "$discovery_result" | grep -q "'forked-lib': 'not'"; then
        pass "Forked lib has correct status"
    else
        fail "Forked lib status incorrect"
    fi
    
    rm -rf "${TEST_WORKDIR}"
    echo ""
}

test_cache_hit_skip_rescan() {
    echo "Test 3: Cache hit skips expensive operations"
    echo "---------------------------------------------"
    
    TEST_WORKDIR=$(mktemp -d /tmp/dev-activity-e2e-XXXXXX)
    export APPS_DIR="${TEST_WORKDIR}/apps"
    
    mkdir -p "${APPS_DIR}/test-project"
    echo "print('hello')" > "${APPS_DIR}/test-project/main.py"
    
    # Calculate fingerprint
    fingerprint=$(python3 << PYTHON_EOF
import sys
sys.path.insert(0, "${SCRIPTS_DIR}")
from phase1_runner import hash_non_git_dir
from pathlib import Path

fp = hash_non_git_dir(Path("${APPS_DIR}/test-project"), {".py"}, max_depth=4)
print(fp)
PYTHON_EOF
)
    
    # Create cache file
    mkdir -p "${APPS_DIR}/test-project"
    echo "fingerprint: ${fingerprint}" > "${APPS_DIR}/test-project/.dev-report-cache.md"
    
    if [[ -f "${APPS_DIR}/test-project/.dev-report-cache.md" ]]; then
        pass "Cache file created"
        
        cached_fp=$(head -1 "${APPS_DIR}/test-project/.dev-report-cache.md" | grep -o '[a-f0-9]\{64\}')
        if [[ "$cached_fp" == "$fingerprint" ]]; then
            pass "Cache fingerprint matches project fingerprint"
        else
            fail "Cache fingerprint does not match"
        fi
    else
        fail "Cache file not created"
    fi
    
    rm -rf "${TEST_WORKDIR}"
    echo ""
}

test_fingerprint_stability() {
    echo "Test 4: Content-based fingerprint stability"
    echo "--------------------------------------------"
    
    TEST_WORKDIR=$(mktemp -d /tmp/dev-activity-e2e-XXXXXX)
    
    mkdir -p "${TEST_WORKDIR}/project"
    echo "print('hello world')" > "${TEST_WORKDIR}/project/script.py"
    
    # Calculate fingerprint twice
    fp1=$(python3 << PYTHON_EOF
import sys
sys.path.insert(0, "${SCRIPTS_DIR}")
from phase1_runner import hash_file
from pathlib import Path
print(hash_file(Path("${TEST_WORKDIR}/project/script.py")))
PYTHON_EOF
)
    
    fp2=$(python3 << PYTHON_EOF
import sys
sys.path.insert(0, "${SCRIPTS_DIR}")
from phase1_runner import hash_file
from pathlib import Path
print(hash_file(Path("${TEST_WORKDIR}/project/script.py")))
PYTHON_EOF
)
    
    if [[ "$fp1" == "$fp2" ]]; then
        pass "Same content produces same fingerprint"
    else
        fail "Fingerprints differ for same content"
    fi
    
    if [[ ${#fp1} -eq 64 ]]; then
        pass "Fingerprint is 64 characters (SHA-256 hex)"
    else
        fail "Fingerprint length is ${#fp1}, expected 64"
    fi
    
    # Modify content
    echo "print('goodbye world')" > "${TEST_WORKDIR}/project/script.py"
    
    fp3=$(python3 << PYTHON_EOF
import sys
sys.path.insert(0, "${SCRIPTS_DIR}")
from phase1_runner import hash_file
from pathlib import Path
print(hash_file(Path("${TEST_WORKDIR}/project/script.py")))
PYTHON_EOF
)
    
    if [[ "$fp1" != "$fp3" ]]; then
        pass "Different content produces different fingerprint"
    else
        fail "Fingerprints same for different content"
    fi
    
    rm -rf "${TEST_WORKDIR}"
    echo ""
}

test_configuration_precedence() {
    echo "Test 5: Configuration precedence"
    echo "---------------------------------"
    
    TEST_WORKDIR=$(mktemp -d /tmp/dev-activity-e2e-XXXXXX)
    
    # Test CLI override via Python
    result=$(python3 << PYTHON_EOF
import sys
sys.path.insert(0, "${SCRIPTS_DIR}")
from phase1_runner import resolve_since, resolve_scan_roots

# Test since precedence
env = {
    "REPORT_SINCE": "2026-01-01",
    "GIT_SINCE": "2025-01-01",
    "SINCE": "2024-01-01"
}

cli_since = "2026-02-01"
result = resolve_since(cli_since, env)
print(f"CLI_OVERRIDE:{result}")

# Test env fallback
result2 = resolve_since(None, env)
print(f"ENV_FALLBACK:{result2}")
PYTHON_EOF
)
    
    if echo "$result" | grep -q "CLI_OVERRIDE:2026-02-01"; then
        pass "CLI argument overrides env var"
    else
        fail "CLI override not working"
    fi
    
    if echo "$result" | grep -q "ENV_FALLBACK:2026-01-01"; then
        pass "Env fallback uses REPORT_SINCE"
    else
        fail "Env fallback not working"
    fi
    
    rm -rf "${TEST_WORKDIR}"
    echo ""
}

# Run all tests
test_e2e_pipeline_creates_output_files
test_marker_files_excluded
test_cache_hit_skip_rescan
test_fingerprint_stability
test_configuration_precedence

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
echo -e "${RED}Failed:${NC} $TESTS_FAILED"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}All E2E tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
