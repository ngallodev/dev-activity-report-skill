#!/usr/bin/env bash
# Delegates to root-level harness for consistency.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "$ROOT_DIR/scripts/run_codex_test_report.sh" "$@"
