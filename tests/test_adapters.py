from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_orchestrator.adapters import DevdocsAdapter, IndexerAdapter, SitemapAdapter
from agentic_orchestrator.config import ToolCommandConfig
from agentic_orchestrator.errors import ConfigurationError, ContractValidationError, ToolExecutionError
from agentic_orchestrator.routing import ToolRequest


def _completed(payload: dict, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["tool"], returncode=returncode, stdout=json.dumps(payload), stderr=stderr)


def _make_executable(tmp_path: Path) -> str:
    script = tmp_path / "tool"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    return str(script)


def test_devdocs_adapter_parses_runtime_contract(tmp_path: Path) -> None:
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
    seen: dict[str, object] = {}

    def runner(**kwargs):
        seen.update(kwargs)
        return _completed(payload)

    adapter = DevdocsAdapter(
        tool_config=ToolCommandConfig(
            name="agentic_devdocs",
            command=[_make_executable(tmp_path)],
            workdir=str(tmp_path),
            extra_args=["-m", "agentic_docs.cli"],
            env={"PYTHONPATH": "src"},
        ),
        runner=runner,
    )
    parsed = adapter.query(db_path="/tmp/devdocs.sqlite", query="docs query")
    assert parsed["tool"] == "agentic_docs"
    assert seen["cwd"] == str(tmp_path)
    assert seen["args"][:3] == [str(tmp_path / "tool"), "-m", "agentic_docs.cli"]
    assert seen["env"]["PYTHONPATH"] == "src"


def test_indexer_adapter_rejects_malformed_contract(tmp_path: Path) -> None:
    malformed = {
        "tool": "agentic_indexer",
        "version": "v1",
        "query": "lookup",
        "normalized_query": "lookup",
        "intent": {},
        "results": [{"id": "broken"}],
    }
    adapter = IndexerAdapter(
        tool_config=ToolCommandConfig(name="agentic_indexer", command=[_make_executable(tmp_path)]),
        runner=lambda **kwargs: _completed(malformed),
    )
    with pytest.raises(ContractValidationError):
        adapter.query(
            db_path="/tmp/index.sqlite",
            request=ToolRequest(tool_name="agentic_indexer", reason="test", mode="build-context-bundle", query="lookup"),
        )


def test_sitemap_adapter_requires_path_context_for_path_lookup(tmp_path: Path) -> None:
    adapter = SitemapAdapter(
        tool_config=ToolCommandConfig(name="agentic_sitemap", command=[_make_executable(tmp_path)]),
        runner=lambda **kwargs: _completed({}),
    )
    with pytest.raises(ConfigurationError):
        adapter.query(
            run_dir="/tmp/run",
            request=ToolRequest(tool_name="agentic_sitemap", reason="test", mode="runtime-query", lookup_mode="path"),
        )


def test_adapter_surfaces_nonzero_exit_clearly(tmp_path: Path) -> None:
    adapter = DevdocsAdapter(
        tool_config=ToolCommandConfig(name="agentic_devdocs", command=[_make_executable(tmp_path)]),
        runner=lambda **kwargs: _completed({}, returncode=2, stderr="boom"),
    )
    with pytest.raises(ToolExecutionError, match="exit code 2"):
        adapter.query(db_path="/tmp/devdocs.sqlite", query="docs query")
