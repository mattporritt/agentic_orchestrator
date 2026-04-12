from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.orchestrator import OrchestratorService


def _payload(tool: str, query: str, file_value: str) -> dict:
    if tool == "agentic_docs":
        return {
            "tool": tool,
            "version": "v1",
            "query": query,
            "normalized_query": query.lower(),
            "intent": {},
            "results": [
                {
                    "id": "docs-1",
                    "type": "knowledge_bundle",
                    "rank": 1,
                    "confidence": "high",
                    "source": {
                        "name": "docs",
                        "type": "documentation",
                        "url": None,
                        "canonical_url": None,
                        "path": "docs/example.md",
                        "document_title": None,
                        "section_title": None,
                        "heading_path": [],
                    },
                    "content": {"summary": "Docs summary", "file_anchors": [file_value]},
                    "diagnostics": {},
                }
            ],
        }
    if tool == "agentic_indexer":
        return {
            "tool": tool,
            "version": "v1",
            "query": query,
            "normalized_query": query.lower(),
            "intent": {},
            "results": [
                {
                    "id": "code-1",
                    "type": "context_bundle",
                    "rank": 1,
                    "confidence": "high",
                    "source": {
                        "name": "index",
                        "type": "code_index",
                        "url": None,
                        "canonical_url": None,
                        "path": file_value,
                        "document_title": None,
                        "section_title": None,
                        "heading_path": [],
                    },
                    "content": {"path": file_value, "symbol": "mod_example\\thing", "summary": "Code summary"},
                    "diagnostics": {},
                }
            ],
        }
    return {
        "tool": tool,
        "version": "v1",
        "query": query,
        "normalized_query": query.lower(),
        "intent": {},
        "results": [
            {
                "id": "site-1",
                "type": "page_context",
                "rank": 1,
                "confidence": "medium",
                "source": {
                    "name": "site",
                    "type": "site_manifest",
                    "url": None,
                    "canonical_url": None,
                    "path": "/course/view.php",
                    "document_title": None,
                    "section_title": None,
                    "heading_path": [],
                },
                "content": {"page_type": "course", "summary": "Site summary"},
                "diagnostics": {},
            }
        ],
    }


def _runner(*, args, text, capture_output, check, cwd=None, env=None):
    del text, capture_output, check, cwd, env
    tool_tag = args[1]
    if tool_tag == "mock-devdocs":
        payload = _payload("agentic_docs", args[3], "settings.php")
    elif tool_tag == "mock-indexer":
        query = args[args.index("--query") + 1] if "--query" in args else args[args.index("--symbol") + 1]
        payload = _payload("agentic_indexer", query, "admin/tool/demo/settings.php")
    else:
        payload = _payload("agentic_sitemap", args[args.index("--query") + 1], "/course/view.php")
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")


def _config() -> OrchestratorConfig:
    executable = "/bin/sh"
    return OrchestratorConfig.from_args(
        Namespace(
            config=None,
            devdocs_cmd=executable,
            devdocs_workdir=None,
            devdocs_extra_args="mock-devdocs",
            indexer_cmd=executable,
            indexer_workdir=None,
            indexer_extra_args="mock-indexer",
            sitemap_cmd=executable,
            sitemap_workdir=None,
            sitemap_extra_args="mock-sitemap",
            devdocs_db_path="/tmp/devdocs.sqlite",
            indexer_db_path="/tmp/index.sqlite",
            sitemap_run_dir="/tmp/sitemap-run",
        )
    )


def test_orchestrator_merges_grouped_results_and_preserves_tool_boundaries() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="add admin settings to a plugin", route_mode="task")
    result = payload["results"][0]
    assert payload["tool"] == "agentic_orchestrator"
    assert result["type"] == "orchestrated_context"
    assert len(result["content"]["docs_results"]) == 1
    assert len(result["content"]["code_results"]) == 1
    assert result["content"]["site_results"] == []
    assert payload["intent"]["route_mode"] == "task"
    assert result["diagnostics"]["tools_called"][0]["tool"] == "agentic_devdocs"
    assert result["diagnostics"]["route_mode"] == "task"
    assert "selected_tools" in result["diagnostics"]
    assert "routing_reasons" in result["diagnostics"]


def test_orchestrator_manual_mode_uses_requested_tools() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(
        query="How should this render in Moodle?",
        route_mode="manual",
        manual_tools=["agentic_indexer", "agentic_sitemap"],
        context={"site_lookup": {"mode": "page_type", "query": "dashboard"}},
    )
    result = payload["results"][0]
    assert result["content"]["docs_results"] == []
    assert len(result["content"]["code_results"]) == 1
    assert len(result["content"]["site_results"]) == 1
    assert payload["intent"]["manual_tools"] == ["agentic_indexer", "agentic_sitemap"]


def test_orchestrator_output_is_deterministic_for_same_inputs() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    first = service.query(query="define a web service", route_mode="task")
    second = service.query(query="define a web service", route_mode="task")
    assert first == second


def test_orchestrator_auto_mode_uses_broader_routing_rules() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="Where do Behat feature files go?", route_mode="auto")
    called = [item["tool"] for item in payload["results"][0]["diagnostics"]["tools_called"]]
    assert called == ["agentic_devdocs", "agentic_indexer"]
