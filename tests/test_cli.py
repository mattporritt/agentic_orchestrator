from __future__ import annotations

import json

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
