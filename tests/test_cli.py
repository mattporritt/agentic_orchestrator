from __future__ import annotations

import json
from pathlib import Path

import agentic_orchestrator.cli as cli


def test_cli_json_mode(monkeypatch, capsys) -> None:
    class FakeService:
        def query(self, *, query: str, context: dict | None = None, route_mode: str = "task", manual_tools: list[str] | None = None) -> dict:
            return {
                "tool": "agentic_orchestrator",
                "version": "v1",
                "query": query,
                "normalized_query": query.lower(),
                "intent": {"route_mode": route_mode, "manual_tools": manual_tools or []},
                "results": [
                    {
                        "id": "1",
                        "type": "orchestrated_context",
                        "rank": 1,
                        "confidence": "high",
                        "source": {
                            "name": "orchestrator",
                            "type": "multi_tool_runtime",
                            "url": None,
                            "canonical_url": None,
                            "path": None,
                            "document_title": None,
                            "section_title": None,
                            "heading_path": [],
                        },
                        "content": {"summary": "ok", "suggested_next_steps": [], "docs_results": [], "code_results": [], "site_results": []},
                        "diagnostics": {"tools_called": [], "selection_strategy": "test", "notes": []},
                    }
                ],
            }

    monkeypatch.setattr(cli.OrchestratorService, "from_config", classmethod(lambda cls, config: FakeService()))
    rc = cli.main(["query", "add admin settings to a plugin", "--json", "--route-mode", "manual", "--tools", "docs,code"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["intent"]["route_mode"] == "manual"
    assert payload["intent"]["manual_tools"] == ["agentic_devdocs", "agentic_indexer"]


def test_cli_plain_mode(monkeypatch, capsys) -> None:
    class FakeService:
        def query(self, *, query: str, context: dict | None = None, route_mode: str = "task", manual_tools: list[str] | None = None) -> dict:
            return {
                "tool": "agentic_orchestrator",
                "version": "v1",
                "query": query,
                "normalized_query": query.lower(),
                "intent": {"route_mode": route_mode, "manual_tools": manual_tools or []},
                "results": [
                    {
                        "id": "1",
                        "type": "orchestrated_context",
                        "rank": 1,
                        "confidence": "high",
                        "source": {
                            "name": "orchestrator",
                            "type": "multi_tool_runtime",
                            "url": None,
                            "canonical_url": None,
                            "path": None,
                            "document_title": None,
                            "section_title": None,
                            "heading_path": [],
                        },
                        "content": {
                            "summary": "Combined context",
                            "suggested_next_steps": [{"kind": "inspect_file", "value": "settings.php", "source_tool": "agentic_indexer"}],
                            "docs_results": [],
                            "code_results": [],
                            "site_results": [],
                        },
                        "diagnostics": {"tools_called": [{"tool": "agentic_indexer"}], "selection_strategy": "test", "notes": []},
                    }
                ],
            }

    monkeypatch.setattr(cli.OrchestratorService, "from_config", classmethod(lambda cls, config: FakeService()))
    rc = cli.main(["query", "add admin settings to a plugin"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "Combined context" in output
    assert "Route mode: task" in output
    assert "agentic_indexer" in output


def test_cli_health_json_mode(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_health_report",
        lambda config, deep=False: {
            "overall_status": "OK",
            "generated_at": "2026-04-14T10:00:00+00:00",
            "deep": deep,
            "checks": [],
            "notes": [],
            "thresholds": {},
        },
    )
    rc = cli.main(["health", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["overall_status"] == "OK"
    assert payload["deep"] is False


def test_cli_health_plain_mode(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_health_report",
        lambda config, deep=False: {
            "overall_status": "WARNING",
            "generated_at": "2026-04-14T10:00:00+00:00",
            "deep": deep,
            "checks": [{"name": "resource.indexer_db", "status": "WARNING", "summary": "stale", "details": {}}],
            "notes": ["warning note"],
            "thresholds": {},
        },
    )
    rc = cli.main(["health", "--deep"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "Overall: WARNING" in output
    assert "Deep checks: enabled" in output
    assert "[WARNING] resource.indexer_db: stale" in output


def test_cli_pilot_run_json_mode(monkeypatch, capsys, tmp_path: Path) -> None:
    class FakeService:
        def query(self, *, query: str, context: dict | None = None, route_mode: str = "task", manual_tools: list[str] | None = None) -> dict:
            return {
                "tool": "agentic_orchestrator",
                "version": "v1",
                "query": query,
                "normalized_query": query.lower(),
                "intent": {"route_mode": route_mode, "manual_tools": manual_tools or []},
                "results": [
                    {
                        "id": "1",
                        "type": "orchestrated_context",
                        "rank": 1,
                        "confidence": "high",
                        "source": {"name": "orchestrator", "type": "multi_tool_runtime", "url": None, "canonical_url": None, "path": None, "document_title": None, "section_title": None, "heading_path": []},
                        "content": {"summary": "pilot", "suggested_next_steps": [], "docs_results": [], "code_results": [], "site_results": []},
                        "diagnostics": {"tools_called": [], "route_mode": route_mode, "routing_reasons": [], "selected_tools": ["agentic_devdocs"], "selection_strategy": "test", "notes": []},
                    }
                ],
            }

    monkeypatch.setattr(cli.OrchestratorService, "from_config", classmethod(lambda cls, config: FakeService()))
    rc = cli.main(["pilot-run", "add admin settings", "--pilot-root", str(tmp_path), "--json", "--task-label", "admin"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task_label"] == "admin"
    assert payload["outcome"]["outcome"] == "not_reviewed"


def test_cli_pilot_report_plain_mode(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_pilot_report",
        lambda pilot_root=None: {
            "pilot_root": pilot_root or "/tmp/pilot",
            "total_runs": 1,
            "by_outcome": {"useful": 1},
            "by_route_mode": {"task": 1},
            "by_task_label": {"admin": 1},
            "by_tools_used": {"agentic_devdocs": 1},
            "trials": [{"trial_id": "one", "created_at": "2026-04-14T00:00:00+00:00", "query": "q", "route_mode": "task", "task_label": "admin", "outcome": "useful", "selected_tools": ["agentic_devdocs"]}],
        },
    )
    rc = cli.main(["pilot-report"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "Pilot Report" in output
    assert "Total runs: 1" in output
