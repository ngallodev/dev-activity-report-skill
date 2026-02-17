"""
Compact test suite for dev-activity-report-skill.

Focus: Critical integration points, caching, error handling, configuration edge cases.
Strategy: Mock all LLM calls, use tmp_path fixtures, test contracts not implementations.

Run: pytest tests/ -v
"""

import sys
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent
        / "skills"
        / "dev-activity-report-skill"
        / "scripts"
    ),
)
