# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Thin subprocess adapters for the runtime-facing sibling tools."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable

from agentic_orchestrator.config import OrchestratorConfig, ToolCommandConfig
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
    workdir: str | None


def default_runner(**kwargs) -> subprocess.CompletedProcess[str]:
    """Default subprocess runner used by adapters."""

    return subprocess.run(**kwargs)


class RuntimeToolAdapter:
    """Base adapter for one runtime-facing subprocess tool."""

    tool_name: str

    def __init__(self, *, tool_config: ToolCommandConfig, runner: Runner | None = None) -> None:
        self.tool_config = tool_config
        self.runner = runner or default_runner

    def _run_json(self, extra_args: list[str]) -> dict:
        self.tool_config.validate()
        command = [self.tool_config.resolved_program(), *(self.tool_config.command[1:]), *(self.tool_config.extra_args or []), *extra_args]
        try:
            completed = self.runner(
                args=command,
                text=True,
                capture_output=True,
                check=False,
                cwd=self.tool_config.workdir,
                env=self.tool_config.merged_env(),
            )
        except FileNotFoundError as exc:
            raise ToolExecutionError(f"{self.tool_name} executable not found: {self.tool_config.command[0]}") from exc

        if completed.returncode != 0:
            raise ToolExecutionError(
                f"{self.tool_name} command failed with exit code {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            loaded = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(f"{self.tool_name} returned invalid JSON: {exc}") from exc
        return validate_runtime_envelope(loaded, expected_tool=self.tool_name)


def validate_debug_runtime_envelope(payload: dict) -> dict:
    """Validate the narrower debugger runtime envelope.

    `agentic_debug` exposes a structured runtime contract, but its top-level
    query/intent/meta fields are debugger-specific and do not match the shared
    string-based sibling envelope used by the docs/index/site tools.
    """

    if not isinstance(payload, dict):
        raise ToolExecutionError("agentic_debug returned a non-object JSON payload.")
    for field in ("tool", "version", "query", "normalized_query", "intent", "results", "diagnostics", "meta"):
        if field not in payload:
            raise ToolExecutionError(f"agentic_debug runtime envelope missing required field '{field}'.")
    if payload["tool"] != "moodle_debug":
        raise ToolExecutionError(f"expected debugger tool 'moodle_debug' but received '{payload['tool']}'.")
    if payload["version"] != "runtime-v1":
        raise ToolExecutionError(f"unsupported agentic_debug runtime version '{payload['version']}'.")
    if not isinstance(payload["results"], list):
        raise ToolExecutionError("agentic_debug runtime envelope field 'results' must be a list.")
    for index, item in enumerate(payload["results"], start=1):
        if not isinstance(item, dict):
            raise ToolExecutionError(f"agentic_debug result {index} must be an object.")
        for field in ("id", "type", "rank", "confidence", "source", "content", "diagnostics"):
            if field not in item:
                raise ToolExecutionError(f"agentic_debug result {index} missing required field '{field}'.")
    return payload


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
            args = [
                "build-context-bundle",
                "--db-path",
                db_path,
                "--limit",
                str(limit),
                "--json-contract",
            ]
            if request.symbol:
                args.extend(["--symbol", request.symbol])
            elif request.file:
                args.extend(["--file", request.file])
            elif request.query:
                args.extend(["--query", request.query])
            else:
                raise ConfigurationError("Indexer build-context-bundle requests require a query, symbol, or file.")
            return self._run_json(args)
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


class DebugAdapter(RuntimeToolAdapter):
    """Adapter for the `agentic_debug` runtime-query and health CLIs."""

    tool_name = "moodle_debug"

    def runtime_query(self, *, request: ToolRequest) -> dict:
        if not request.payload:
            raise ConfigurationError("Debug runtime-query requests require a JSON payload.")
        return self._run_debug_json(["runtime-query", "--json", json.dumps(request.payload, separators=(",", ":"))])

    def health(self) -> dict:
        return self._run_debug_json(["health", "--json", "{}"])

    def _run_debug_json(self, extra_args: list[str]) -> dict:
        self.tool_config.validate()
        command = [self.tool_config.resolved_program(), *(self.tool_config.command[1:]), *(self.tool_config.extra_args or []), *extra_args]
        try:
            completed = self.runner(
                args=command,
                text=True,
                capture_output=True,
                check=False,
                cwd=self.tool_config.workdir,
                env=self.tool_config.merged_env(),
            )
        except FileNotFoundError as exc:
            raise ToolExecutionError(f"{self.tool_name} executable not found: {self.tool_config.command[0]}") from exc

        if completed.returncode != 0:
            raise ToolExecutionError(
                f"{self.tool_name} command failed with exit code {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            loaded = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(f"{self.tool_name} returned invalid JSON: {exc}") from exc
        return validate_debug_runtime_envelope(loaded)


@dataclass
class AdapterSet:
    devdocs: DevdocsAdapter
    indexer: IndexerAdapter
    sitemap: SitemapAdapter
    debug: DebugAdapter

    @classmethod
    def from_config(cls, config: OrchestratorConfig, runner: Runner | None = None) -> "AdapterSet":
        return cls(
            devdocs=DevdocsAdapter(tool_config=config.devdocs, runner=runner),
            indexer=IndexerAdapter(tool_config=config.indexer, runner=runner),
            sitemap=SitemapAdapter(tool_config=config.sitemap, runner=runner),
            debug=DebugAdapter(tool_config=config.debug, runner=runner),
        )


def tool_call_record(config: OrchestratorConfig, request: ToolRequest) -> ToolCallRecord:
    """Build a deterministic record of one routed tool request."""

    tool_config = config.tool_config(request.tool_name)
    if request.tool_name == "agentic_devdocs":
        cmd = [*tool_config.command, *(tool_config.extra_args or []), "query"]
    elif request.tool_name == "agentic_indexer":
        cmd = [*tool_config.command, *(tool_config.extra_args or []), request.mode]
    elif request.tool_name == "agentic_sitemap":
        cmd = [*tool_config.command, *(tool_config.extra_args or []), "runtime-query"]
    elif request.tool_name == "agentic_debug":
        cmd = [*tool_config.command, *(tool_config.extra_args or []), request.mode]
    else:
        cmd = tool_config.command_line()
    return ToolCallRecord(tool=request.tool_name, mode=request.mode, reason=request.reason, command=cmd, workdir=tool_config.workdir)
