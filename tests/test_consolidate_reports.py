import json
from pathlib import Path


def test_merge_json_reports_dedupes_and_keeps_insights(tmp_path):
    from consolidate_reports import merge_json_reports

    r1 = tmp_path / "dev-activity-report-1.json"
    r2 = tmp_path / "dev-activity-report-2.json"

    payload = {
        "schema_version": "dev-activity-report.v1",
        "sections": {
            "overview": {"bullets": ["Did A"]},
            "key_changes": [{"title": "Change", "project_id": None, "bullets": ["X"], "tags": []}],
            "recommendations": [{"text": "Do B", "priority": "medium", "evidence_project_ids": []}],
            "resume_bullets": [{"text": "Built C", "evidence_project_ids": []}],
            "linkedin": {"sentences": ["Sentence 1"]},
            "highlights": [{"title": "H1", "rationale": "R1", "evidence_project_ids": []}],
            "timeline": [{"date": "2026-02-18", "event": "Event", "project_ids": []}],
            "tech_inventory": {"languages": ["Python"], "frameworks": [], "ai_tools": ["Claude"], "infra": []},
        },
        "insights": {
            "source": {"report_link": "file:///tmp/report.html"},
            "sections": [{"section_id": "wins", "title": "Wins", "link": "file:///tmp/report.html#wins", "content": ["Won big"]}],
            "quotes": [{"quote": "Great work", "source_path": "/tmp/report.html", "source_link": "file:///tmp/report.html"}],
        },
    }
    r1.write_text(json.dumps(payload), encoding="utf-8")
    r2.write_text(json.dumps(payload), encoding="utf-8")

    merged = merge_json_reports([r1, r2], "Aggregate")
    assert merged["schema_version"] == "dev-activity-report.v1"
    assert merged["sections"]["overview"]["bullets"] == ["Did A"]
    assert len(merged["sections"]["resume_bullets"]) == 1
    assert len(merged["insights"]["quotes"]) == 1
    assert merged["insights"]["sections"][0]["title"] == "Wins"


def test_write_outputs_emits_html(tmp_path):
    from consolidate_reports import write_outputs

    report_obj = {
        "schema_version": "dev-activity-report.v1",
        "generated_at": "2026-02-18T00:00:00Z",
        "resume_header": "Aggregate",
        "sections": {
            "overview": {"bullets": ["A"]},
            "key_changes": [],
            "recommendations": [],
            "resume_bullets": [],
            "linkedin": {"sentences": []},
            "highlights": [],
            "timeline": [],
            "tech_inventory": {"languages": [], "frameworks": [], "ai_tools": [], "infra": []},
        },
        "insights": {"source": {}, "sections": [], "quotes": []},
    }
    base = tmp_path / "agg"
    written = write_outputs(report_obj, base, ["json", "md", "html"])
    paths = {p.suffix for p in written}
    assert ".json" in paths
    assert ".md" in paths
    assert ".html" in paths
    assert (tmp_path / "agg.html").exists()
