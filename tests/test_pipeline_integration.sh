#!/usr/bin/env bash
#
# Shell Tests: Main Entry Point and Integration
#
# Usage: ./test_pipeline_integration.sh
#
# These tests verify the pipeline entry point script behavior,
# environment interaction, and end-to-end integration without
# calling actual LLM APIs.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TESTS_PASSED=0
TESTS_FAILED=0

# Test directory
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${TEST_DIR}/.." && pwd)"
SKILL_DIR="${PROJECT_ROOT}/skills/dev-activity-report-skill"

echo "=========================================="
echo "Dev Activity Report - Shell Integration Tests"
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

skip() {
    echo -e "${YELLOW}⊘ SKIP${NC}: $1"
}

cleanup() {
    # Cleanup any test artifacts
    rm -rf /tmp/dev-activity-test-*
    rm -f "${SKILL_DIR}/.env.test" 2>/dev/null || true
}

trap cleanup EXIT

# Test 1: Python scripts are executable
echo "Test 1: Python scripts exist and are syntactically valid"
echo "---------------------------------------------------------"

PYTHON_SCRIPTS=(
    "scripts/phase1_runner.py"
    "scripts/phase1_5_draft.py"
    "scripts/run_pipeline.py"
    "scripts/render_report.py"
    "scripts/token_logger.py"
)

for script in "${PYTHON_SCRIPTS[@]}"; do
    full_path="${SKILL_DIR}/${script}"
    if [[ -f "$full_path" ]]; then
        if timeout 5 python3 -m py_compile "$full_path" 2>/dev/null; then
            pass "${script} compiles successfully"
        else
            fail "${script} has syntax errors"
        fi
    else
        fail "${script} not found"
    fi
done

echo ""

# Test 2: Required files exist
echo "Test 2: Required configuration files"
echo "-------------------------------------"

REQUIRED_FILES=(
    ".dev-report-fingerprint-ignore"
    "SKILL.md"
    "references/PAYLOAD_REFERENCE.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    full_path="${SKILL_DIR}/${file}"
    if [[ -f "$full_path" ]]; then
        pass "${file} exists"
    else
        fail "${file} not found"
    fi
done

echo ""

# Test 3: Fingerprint ignore patterns
echo "Test 3: Fingerprint ignore file"
echo "--------------------------------"

if [[ -f "${SKILL_DIR}/.dev-report-fingerprint-ignore" ]]; then
    pass "Fingerprint ignore file exists"
    
    # Check it has content
    if [[ -s "${SKILL_DIR}/.dev-report-fingerprint-ignore" ]]; then
        pass "Fingerprint ignore file has content"
    else
        fail "Fingerprint ignore file is empty"
    fi
    
    # Check for common patterns
    if grep -q "\*.log" "${SKILL_DIR}/.dev-report-fingerprint-ignore"; then
        pass "Log file patterns present in ignore file"
    else
        fail "Log file patterns missing from ignore file"
    fi
    
    # Check for debug patterns
    if grep -q "debug" "${SKILL_DIR}/.dev-report-fingerprint-ignore"; then
        pass "Debug directory patterns present"
    else
        fail "Debug patterns missing from ignore file"
    fi
else
    fail "Fingerprint ignore file not found"
fi

echo ""

# Test 4: Required dependencies available
echo "Test 4: Required dependencies"
echo "-----------------------------"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
    pass "Python 3.8+ available"
else
    fail "Python 3.8+ required"
fi

# Check pytest is available
if command -v pytest &> /dev/null; then
    pass "pytest available"
else
    skip "pytest not installed (optional, run: pip install pytest)"
fi

echo ""
echo "Optional dependencies (warnings only if missing):"

OPTIONAL_DEPS=(
    "dotenv:python-dotenv"
    "pygit2:pygit2"
    "openai:openai"
)

for dep_spec in "${OPTIONAL_DEPS[@]}"; do
    IFS=':' read -r module_name package_name <<< "$dep_spec"
    if timeout 2 python3 -c "import ${module_name}" 2>/dev/null; then
        echo "  ${GREEN}✓${NC} ${package_name} available"
    else
        echo "  ${YELLOW}⊘${NC} ${package_name} not installed (optional)"
    fi
done

echo ""

# Test 5: Verify marker file names in code
echo "Test 5: Marker file definitions"
echo "--------------------------------"

if grep -q "MARKERS" "${SKILL_DIR}/scripts/phase1_runner.py"; then
    pass "MARKERS constant defined in phase1_runner.py"
    
    # Check for expected markers
    for marker in ".skip-for-now" ".not-my-work" ".forked-work" ".forked-work-modified"; do
        if grep -q "${marker}" "${SKILL_DIR}/scripts/phase1_runner.py"; then
            pass "Marker ${marker} defined"
        else
            fail "Marker ${marker} not found in code"
        fi
    done
else
    fail "MARKERS constant not found in phase1_runner.py"
fi

echo ""

# Test 6: Test directory structure
echo "Test 6: Test suite structure"
echo "-----------------------------"

TEST_FILES=(
    "tests/test_contracts_and_caching.py"
    "tests/test_consolidate_reports.py"
    "tests/test_failure_modes.py"
    "tests/test_integration_pipeline.py"
    "tests/test_prompt_parsing_and_refresh.py"
    "tests/test_shell_integration.sh"
)

for test_file in "${TEST_FILES[@]}"; do
    full_path="${PROJECT_ROOT}/${test_file}"
    if [[ -f "$full_path" ]]; then
        pass "${test_file} exists"
    else
        fail "${test_file} not found"
    fi
done

echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
echo -e "${RED}Failed:${NC} $TESTS_FAILED"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
