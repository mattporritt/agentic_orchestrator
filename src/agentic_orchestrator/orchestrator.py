"""Thin orchestration service for combining docs, code, and site runtime outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_orchestrator.adapters import AdapterSet, ToolCallRecord, tool_call_record
from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.contract import build_orchestrator_envelope
from agentic_orchestrator.errors import ConfigurationError, ToolExecutionError
from agentic_orchestrator.routing import RoutingDecision, ToolRequest, route_query


@dataclass
class OrchestratorService:
    """Coordinate routing, adapter execution, and grouped result merging."""

    config: OrchestratorConfig
    adapters: AdapterSet

    @classmethod
    def from_config(cls, config: OrchestratorConfig, runner=None) -> "OrchestratorService":
        return cls(config=config, adapters=AdapterSet.from_config(config, runner=runner))

    def query(
        self,
        *,
        query: str,
        context: dict[str, Any] | None = None,
        route_mode: str = "task",
        manual_tools: list[str] | None = None,
    ) -> dict[str, Any]:
        decision = route_query(query, context=context, route_mode=route_mode, manual_tools=manual_tools)
        docs_payload: dict[str, Any] | None = None
        code_payload: dict[str, Any] | None = None
        site_payload: dict[str, Any] | None = None
        records: list[ToolCallRecord] = []
        failures: list[dict[str, str]] = []

        for request in decision.tools:
            records.append(tool_call_record(self.config, request))
            try:
                payload = self._run_request(request)
            except (ConfigurationError, ToolExecutionError) as exc:
                failures.append({"tool": request.tool_name, "mode": request.mode, "error": str(exc)})
                continue
            if request.tool_name == "agentic_devdocs":
                docs_payload = payload
            elif request.tool_name == "agentic_indexer":
                code_payload = payload
            elif request.tool_name == "agentic_sitemap":
                site_payload = payload

        if not any((docs_payload, code_payload, site_payload)) and failures:
            messages = "; ".join(f"{item['tool']}: {item['error']}" for item in failures)
            raise ToolExecutionError(f"No tool calls succeeded. {messages}")

        docs_results = list((docs_payload or {}).get("results", []))
        code_results = list((code_payload or {}).get("results", []))
        site_results = list((site_payload or {}).get("results", []))
        assembly = self._build_assembly_evidence(docs_results, code_results, site_results)
        notes = self._build_notes(decision, docs_payload, code_payload, site_payload, failures)
        summary = self._build_summary(docs_results, code_results, site_results, assembly["key_signals"])
        next_steps = assembly["suggested_next_steps"]
        intent = self._build_intent(decision)
        tools_called = [self._serialize_record(item) for item in records]

        payload = build_orchestrator_envelope(
            query=query,
            intent=intent,
            docs_results=docs_results,
            code_results=code_results,
            site_results=site_results,
            key_signals=assembly["key_signals"],
            tools_called=tools_called,
            suggested_next_steps=next_steps,
            summary=summary,
            notes=notes + [f"tool_failure: {item['tool']} {item['mode']} {item['error']}" for item in failures],
        )
        diagnostics = payload["results"][0]["diagnostics"]
        diagnostics["route_mode"] = decision.route_mode
        diagnostics["routing_reasons"] = decision.routing_reasons
        diagnostics["matched_route_signals"] = decision.routing_reasons
        diagnostics["selected_tools"] = [request.tool_name for request in decision.tools]
        diagnostics["assembly_notes"] = assembly["assembly_notes"]
        return payload

    def _run_request(self, request: ToolRequest) -> dict[str, Any]:
        if request.tool_name == "agentic_devdocs":
            return self.adapters.devdocs.query(db_path=str(self.config.devdocs_db_path or ""), query=str(request.query or ""))
        if request.tool_name == "agentic_indexer":
            return self.adapters.indexer.query(db_path=str(self.config.indexer_db_path or ""), request=request)
        if request.tool_name == "agentic_sitemap":
            return self.adapters.sitemap.query(run_dir=str(self.config.sitemap_run_dir or ""), request=request)
        raise ValueError(f"Unsupported tool request for '{request.tool_name}'.")

    def _build_intent(self, decision: RoutingDecision) -> dict[str, Any]:
        return {
            "route_mode": decision.route_mode,
            "task_type": decision.task_type,
            "component_hint": decision.component_hint,
            "source_preferences": decision.source_preferences,
            "tools_considered": [request.tool_name for request in decision.tools],
            "routing_notes": decision.routing_notes,
            "manual_tools": decision.manual_tools,
        }

    def _build_notes(
        self,
        decision: RoutingDecision,
        docs_payload: dict[str, Any] | None,
        code_payload: dict[str, Any] | None,
        site_payload: dict[str, Any] | None,
        failures: list[dict[str, str]],
    ) -> list[str]:
        notes = [
            f"routed task type: {decision.task_type}",
            f"route mode: {decision.route_mode}",
            f"routing reasons: {', '.join(decision.routing_reasons)}",
        ]
        for tool_name, payload in (
            ("agentic_devdocs", docs_payload),
            ("agentic_indexer", code_payload),
            ("agentic_sitemap", site_payload),
        ):
            if payload is None:
                continue
            notes.append(f"{tool_name} returned {len(payload.get('results', []))} result(s)")
        if failures:
            notes.append(f"tool failures: {len(failures)}")
        return notes

    def _build_summary(
        self,
        docs_results: list[dict[str, Any]],
        code_results: list[dict[str, Any]],
        site_results: list[dict[str, Any]],
        key_signals: list[dict[str, str]],
    ) -> str:
        parts = [
            f"docs={len(docs_results)}",
            f"code={len(code_results)}",
            f"site={len(site_results)}",
        ]
        promoted = [signal["value"] for signal in key_signals[:4] if isinstance(signal.get("value"), str)]
        if promoted:
            return f"Combined context from {sum(bool(group) for group in (docs_results, code_results, site_results))} tool(s) ({', '.join(parts)}). Key signals: {' | '.join(promoted)}"
        top_summaries: list[str] = []
        for group in (docs_results, code_results, site_results):
            if not group:
                continue
            content = group[0].get("content", {})
            summary = content.get("summary")
            if isinstance(summary, str) and summary:
                top_summaries.append(summary)
        if top_summaries:
            return f"Combined context from {sum(bool(group) for group in (docs_results, code_results, site_results))} tool(s) ({', '.join(parts)}). Top signals: {' | '.join(top_summaries[:2])}"
        return f"Combined context from {sum(bool(group) for group in (docs_results, code_results, site_results))} tool(s) ({', '.join(parts)})."

    def _build_assembly_evidence(
        self,
        docs_results: list[dict[str, Any]],
        code_results: list[dict[str, Any]],
        site_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evidence: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        filtered_count = 0

        for result in docs_results[:3]:
            source = result.get("source", {})
            content = result.get("content", {})
            path = source.get("path")
            if isinstance(path, str) and path:
                self._add_evidence(evidence, seen, "read_doc", path, "agentic_devdocs")
            for anchor in list(content.get("file_anchors", []))[:2]:
                if isinstance(anchor, str) and anchor:
                    if self._is_noisy_path(anchor):
                        filtered_count += 1
                        continue
                    kind = "read_doc" if anchor.endswith(".md") else "inspect_file"
                    self._add_evidence(evidence, seen, kind, anchor, "agentic_devdocs")

        for result in code_results[:4]:
            content = result.get("content", {})
            self._add_code_evidence(evidence, seen, content)

        for result in site_results[:3]:
            source = result.get("source", {})
            content = result.get("content", {})
            page_type = content.get("to_page_type") or source.get("section_title") or content.get("page_type")
            if isinstance(page_type, str) and page_type:
                self._add_evidence(evidence, seen, "inspect_page_type", page_type, "agentic_sitemap")
            path_length = content.get("path_length")
            if isinstance(path_length, int):
                self._add_evidence(evidence, seen, "check_workflow", f"path_length={path_length}", "agentic_sitemap")
            for step in list(content.get("next_steps", []))[:2]:
                if isinstance(step, dict):
                    target_page_type = step.get("target_page_type")
                    if isinstance(target_page_type, str) and target_page_type:
                        self._add_evidence(evidence, seen, "inspect_page_type", target_page_type, "agentic_sitemap")

        key_signals = evidence[:6]
        suggested_next_steps = evidence[:10]
        assembly_notes = [
            f"key_signal_count={len(key_signals)}",
            f"suggested_next_step_count={len(suggested_next_steps)}",
        ]
        if filtered_count:
            assembly_notes.append(f"filtered_noisy_paths={filtered_count}")
        return {
            "key_signals": key_signals,
            "suggested_next_steps": suggested_next_steps,
            "assembly_notes": assembly_notes,
        }

    def _add_code_evidence(
        self,
        evidence: list[dict[str, str]],
        seen: set[tuple[str, str]],
        content: dict[str, Any],
    ) -> None:
        for key in ("file", "path"):
            value = content.get(key)
            if isinstance(value, str) and value and not self._is_noisy_path(value):
                self._add_evidence(evidence, seen, "inspect_file", value, "agentic_indexer")
        for key in ("fqname", "symbol", "name"):
            value = content.get(key)
            if isinstance(value, str) and value:
                self._add_evidence(evidence, seen, "inspect_symbol", value, "agentic_indexer")
                break
        for bucket in ("primary_context", "example_patterns", "optional_context", "supporting_context", "tests_to_consider"):
            for item in list(content.get(bucket, []))[:3]:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                symbol = item.get("symbol")
                if isinstance(path, str) and path and not self._is_noisy_path(path):
                    self._add_evidence(evidence, seen, "inspect_file", path, "agentic_indexer")
                if isinstance(symbol, str) and symbol:
                    self._add_evidence(evidence, seen, "inspect_symbol", symbol, "agentic_indexer")

    def _add_evidence(
        self,
        evidence: list[dict[str, str]],
        seen: set[tuple[str, str]],
        kind: str,
        value: str,
        source_tool: str,
    ) -> None:
        key = (kind, value)
        if key in seen:
            return
        seen.add(key)
        evidence.append({"kind": kind, "value": value, "source_tool": source_tool})

    def _is_noisy_path(self, value: str) -> bool:
        return value.startswith("//") or "://" in value or value.startswith("../")

    def _serialize_record(self, item: ToolCallRecord) -> dict[str, Any]:
        return {
            "tool": item.tool,
            "mode": item.mode,
            "reason": item.reason,
            "command": item.command,
            "workdir": item.workdir,
        }
