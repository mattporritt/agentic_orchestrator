"""Thin subprocess adapters for the three existing runtime-facing tools."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.contract import validate_runtime_envelope
from agentic_orchestrator.errors import ConfigurationError, ToolExecutionError
from agentic_orchestrator.routing import ToolRequest


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class ToolCallRecord:
    tool: str
    mode: str
    reason: str
    command: list[str]


def default_runner(**kwargs) -> subprocess.CompletedProcess[str]:
    """Default subprocess runner used by adapters."""

    return subprocess.run(**kwargs)


class RuntimeToolAdapter:
    """Base adapter for one runtime-facing subprocess tool."""

    tool_name: str

    def __init__(self, *, command: list[str], runner: Runner | None = None) -> None:
        self.command = list(command)
        self.runner = runner or default_runner

    def _run_json(self, extra_args: list[str]) -> dict:
        try:
            completed = self.runner(
                args=[*self.command, *extra_args],
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ToolExecutionError(f"{self.tool_name} executable not found: {self.command[0]}") from exc

        if completed.returncode != 0:
            raise ToolExecutionError(
                f"{self.tool_name} command failed with exit code {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            loaded = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(f"{self.tool_name} returned invalid JSON: {exc}") from exc
        return validate_runtime_envelope(loaded, expected_tool=self.tool_name)


class DevdocsAdapter(RuntimeToolAdapter):
    """Adapter for the `agentic_devdocs` runtime contract CLI."""

    tool_name = "agentic_docs"

    def query(self, *, db_path: str, query: str, top_k: int = 5) -> dict:
        if not db_path:
            raise ConfigurationError("Devdocs queries require a configured devdocs DB path.")
        return self._run_json(["query", query, "--db-path", db_path, "--top-k", str(top_k), "--json-contract"])


class IndexerAdapter(RuntimeToolAdapter):
    """Adapter for the `agentic_indexer` runtime contract CLI subset."""

    tool_name = "agentic_indexer"

    def query(self, *, db_path: str, request: ToolRequest, limit: int = 6) -> dict:
        if not db_path:
            raise ConfigurationError("Indexer queries require a configured indexer DB path.")
        if request.mode == "find-definition":
            if not request.symbol:
                raise ConfigurationError("Indexer find-definition requests require a symbol.")
            return self._run_json(
                [
                    "find-definition",
                    "--db-path",
                    db_path,
                    "--symbol",
                    request.symbol,
                    "--limit",
                    str(limit),
                    "--json-contract",
                ]
            )
        if request.mode == "build-context-bundle":
            if not request.query:
                raise ConfigurationError("Indexer build-context-bundle requests require a query.")
            return self._run_json(
                [
                    "build-context-bundle",
                    "--db-path",
                    db_path,
                    "--query",
                    request.query,
                    "--limit",
                    str(limit),
                    "--json-contract",
                ]
            )
        if request.mode == "semantic-context":
            if not request.query:
                raise ConfigurationError("Indexer semantic-context requests require a query.")
            return self._run_json(
                [
                    "semantic-context",
                    "--db-path",
                    db_path,
                    "--query",
                    request.query,
                    "--limit",
                    str(limit),
                    "--json-contract",
                ]
            )
        raise ConfigurationError(f"Unsupported indexer mode '{request.mode}'.")


class SitemapAdapter(RuntimeToolAdapter):
    """Adapter for the `agentic_sitemap` runtime query CLI."""

    tool_name = "agentic_sitemap"

    def query(self, *, run_dir: str, request: ToolRequest, top_k: int = 4) -> dict:
        if not run_dir:
            raise ConfigurationError("Sitemap queries require a configured sitemap run directory.")
        args = [
            "runtime-query",
            "--run",
            run_dir,
            "--lookup-mode",
            str(request.lookup_mode or "page"),
            "--top-k",
            str(top_k),
            "--json-contract",
        ]
        if request.lookup_mode == "path":
            if not request.from_page or not request.to_page:
                raise ConfigurationError("Sitemap path lookups require from_page and to_page.")
            args.extend(["--from-page", request.from_page, "--to-page", request.to_page])
        else:
            if not request.query:
                raise ConfigurationError("Sitemap runtime queries require a lookup query.")
            args.extend(["--query", request.query])
        return self._run_json(args)


@dataclass
class AdapterSet:
    devdocs: DevdocsAdapter
    indexer: IndexerAdapter
    sitemap: SitemapAdapter

    @classmethod
    def from_config(cls, config: OrchestratorConfig, runner: Runner | None = None) -> "AdapterSet":
        return cls(
            devdocs=DevdocsAdapter(command=config.devdocs.command, runner=runner),
            indexer=IndexerAdapter(command=config.indexer.command, runner=runner),
            sitemap=SitemapAdapter(command=config.sitemap.command, runner=runner),
        )


def tool_call_record(config: OrchestratorConfig, request: ToolRequest) -> ToolCallRecord:
    """Build a deterministic record of one routed tool request."""

    if request.tool_name == "agentic_devdocs":
        cmd = [*config.devdocs.command, "query"]
    elif request.tool_name == "agentic_indexer":
        cmd = [*config.indexer.command, request.mode]
    elif request.tool_name == "agentic_sitemap":
        cmd = [*config.sitemap.command, "runtime-query"]
    else:
        cmd = [request.tool_name]
    return ToolCallRecord(tool=request.tool_name, mode=request.mode, reason=request.reason, command=cmd)
