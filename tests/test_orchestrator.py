from __future__ import annotations

import json
import subprocess
from argparse import Namespace

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


def _runner(*, args, text, capture_output, check):
    binary = args[0]
    if binary == "mock-devdocs":
        payload = _payload("agentic_docs", args[2], "settings.php")
    elif binary == "mock-indexer":
        payload = _payload("agentic_indexer", args[args.index("--query") + 1], "admin/tool/demo/settings.php")
    else:
        payload = _payload("agentic_sitemap", args[args.index("--query") + 1], "/course/view.php")
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")


def _config() -> OrchestratorConfig:
    return OrchestratorConfig.from_args(
        Namespace(
            devdocs_cmd="mock-devdocs",
            indexer_cmd="mock-indexer",
            sitemap_cmd="mock-sitemap",
            devdocs_db_path="/tmp/devdocs.sqlite",
            indexer_db_path="/tmp/index.sqlite",
            sitemap_run_dir="/tmp/sitemap-run",
        )
    )


def test_orchestrator_merges_grouped_results_and_preserves_tool_boundaries() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="add admin settings to a plugin")
    result = payload["results"][0]
    assert payload["tool"] == "agentic_orchestrator"
    assert result["type"] == "orchestrated_context"
    assert len(result["content"]["docs_results"]) == 1
    assert len(result["content"]["code_results"]) == 1
    assert result["content"]["site_results"] == []
    assert result["diagnostics"]["tools_called"][0]["tool"] == "agentic_devdocs"
    assert result["content"]["suggested_next_steps"][0]["kind"] in {"read_doc", "inspect_file"}


def test_orchestrator_render_flow_adds_site_results() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="How should this render in Moodle?")
    result = payload["results"][0]
    assert len(result["content"]["site_results"]) == 1
    assert [call["tool"] for call in result["diagnostics"]["tools_called"]] == [
        "agentic_devdocs",
        "agentic_indexer",
        "agentic_sitemap",
    ]


def test_orchestrator_output_is_deterministic_for_same_inputs() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    first = service.query(query="define a web service")
    second = service.query(query="define a web service")
    assert first == second
