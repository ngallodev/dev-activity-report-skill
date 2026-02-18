"""
Shared test fixtures for dev-activity-report-skill integration tests.

This module provides factory functions for creating valid test data
that conforms to the JSON schemas in tests/contracts/.
"""

import json
from pathlib import Path
from typing import Any


def load_schema(schema_name: str) -> dict:
    """Load a JSON schema by name."""
    schema_path = Path(__file__).parent.parent / "contracts" / f"{schema_name}.schema.json"
    return json.loads(schema_path.read_text())


def valid_phase1_output(**overrides: Any) -> dict:
    """
    Return a minimal valid Phase 1 output.
    
    Args:
        **overrides: Key-value pairs to override default values
        
    Returns:
        dict conforming to phase1_output.schema.json
    """
    data = {
        "ts": "2024-01-15T10:00:00Z",
        "ad": "/test/apps",
        "mk": [],
        "p": [
            {
                "n": "test-proj",
                "pt": "/test/apps/test-proj",
                "fp": "a" * 64,
                "st": "orig",
                "cc": 5,
                "sd": "3 files changed, 10 insertions(+)",
                "fc": ["main.py"],
                "msg": ["Initial commit"],
                "hl": ["feature"]
            }
        ],
        "x": [],
        "cl": {"sk": [], "hk": [], "ag": []},
        "cx": {"sm": {}, "cw": [], "sk": []},
        "ins": [],
        "stats": {"total": 1, "stale": 1, "cached": 0}
    }
    data.update(overrides)
    return data


def valid_phase15_output(**overrides: Any) -> dict:
    """Return a minimal valid Phase 1.5 draft output."""
    data = {
        "draft": "- test-proj: 5 commits; themes: feature\nOverview: test project updates",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        "cost": None
    }
    data.update(overrides)
    return data


def valid_phase2_output(**overrides: Any) -> dict:
    """
    Return a minimal valid Phase 2 output.
    
    Args:
        **overrides: Key-value pairs to override default values
        
    Returns:
        dict conforming to phase2_output.schema.json
    """
    data = {
        "sections": {
            "overview": {"bullets": ["Shipped feature X"]},
            "key_changes": [
                {
                    "title": "Feature X",
                    "bullets": ["Implemented core functionality"],
                    "project_id": None,
                    "tags": []
                }
            ],
            "recommendations": [
                {
                    "text": "Refactor module A",
                    "priority": "medium",
                    "evidence_project_ids": []
                }
            ],
            "resume_bullets": [
                {
                    "text": "Led development of feature X",
                    "evidence_project_ids": []
                }
            ],
            "linkedin": {
                "sentences": ["Excited to share my recent work on feature X."]
            },
            "highlights": [
                {
                    "title": "Performance Improvement",
                    "rationale": "Reduced P99 latency by 50%",
                    "evidence_project_ids": []
                }
            ],
            "timeline": [
                {
                    "date": "2024-01-15",
                    "event": "Launched feature X",
                    "project_ids": []
                }
            ],
            "tech_inventory": {
                "languages": ["Python", "TypeScript"],
                "frameworks": ["FastAPI"],
                "ai_tools": ["Claude"],
                "infra": ["Docker"]
            }
        },
        "render_hints": {
            "preferred_outputs": ["md"],
            "style": "concise",
            "tone": "professional"
        }
    }
    data.update(overrides)
    return data


def project_with_status(status: str) -> dict:
    """Return a project dict with the specified status."""
    return {
        "n": f"proj-{status}",
        "pt": f"/test/apps/proj-{status}",
        "fp": "b" * 64,
        "st": status,
        "cc": 3,
        "sd": "2 files changed",
        "fc": ["file.py"],
        "msg": ["commit message"],
        "hl": []
    }


def marker(marker_type: str, project: str) -> dict:
    """Return a marker dict."""
    return {
        "m": marker_type,
        "p": project,
        "path": f"/test/apps/{project}/{marker_type}",
        "r": "/test/apps"
    }
