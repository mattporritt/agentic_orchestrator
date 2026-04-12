from __future__ import annotations

import json
import subprocess

import pytest

from agentic_orchestrator.adapters import DevdocsAdapter, IndexerAdapter, SitemapAdapter
from agentic_orchestrator.errors import ConfigurationError, ContractValidationError, ToolExecutionError
from agentic_orchestrator.routing import ToolRequest


def _completed(payload: dict, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["tool"], returncode=returncode, stdout=json.dumps(payload), stderr=stderr)


def test_devdocs_adapter_parses_runtime_contract() -> None:
    payload = {
        "tool": "agentic_docs",
        "version": "v1",
        "query": "docs query",
        "normalized_query": "docs query",
        "intent": {},
        "results": [
            {
                "id": "1",
                "type": "knowledge_bundle",
                "rank": 1,
                "confidence": "high",
                "source": {
                    "name": "docs",
                    "type": "documentation",
                    "url": None,
                    "canonical_url": None,
                    "path": "docs/test.md",
                    "document_title": None,
                    "section_title": None,
                    "heading_path": [],
                },
                "content": {},
                "diagnostics": {},
            }
        ],
    }
    adapter = DevdocsAdapter(command=["agentic-docs"], runner=lambda **kwargs: _completed(payload))
    parsed = adapter.query(db_path="/tmp/devdocs.sqlite", query="docs query")
    assert parsed["tool"] == "agentic_docs"
    assert parsed["results"][0]["type"] == "knowledge_bundle"


def test_indexer_adapter_rejects_malformed_contract() -> None:
    malformed = {
        "tool": "agentic_indexer",
        "version": "v1",
        "query": "lookup",
        "normalized_query": "lookup",
        "intent": {},
        "results": [{"id": "broken"}],
    }
    adapter = IndexerAdapter(command=["moodle-indexer"], runner=lambda **kwargs: _completed(malformed))
    with pytest.raises(ContractValidationError):
        adapter.query(
            db_path="/tmp/index.sqlite",
            request=ToolRequest(tool_name="agentic_indexer", reason="test", mode="build-context-bundle", query="lookup"),
        )


def test_sitemap_adapter_requires_path_context_for_path_lookup() -> None:
    adapter = SitemapAdapter(command=["moodle-sitemap"], runner=lambda **kwargs: _completed({}))
    with pytest.raises(ConfigurationError):
        adapter.query(
            run_dir="/tmp/run",
            request=ToolRequest(tool_name="agentic_sitemap", reason="test", mode="runtime-query", lookup_mode="path"),
        )


def test_adapter_surfaces_nonzero_exit_clearly() -> None:
    adapter = DevdocsAdapter(
        command=["agentic-docs"],
        runner=lambda **kwargs: _completed({}, returncode=2, stderr="boom"),
    )
    with pytest.raises(ToolExecutionError, match="exit code 2"):
        adapter.query(db_path="/tmp/devdocs.sqlite", query="docs query")
