"""Explicit first-pass rule-based routing for the thin orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_orchestrator.contract import normalize_query


@dataclass(frozen=True)
class ToolRequest:
    tool_name: str
    reason: str
    mode: str
    query: str | None = None
    symbol: str | None = None
    lookup_mode: str | None = None
    from_page: str | None = None
    to_page: str | None = None


@dataclass(frozen=True)
class RoutingDecision:
    task_type: str
    component_hint: str | None
    source_preferences: list[str]
    tools: list[ToolRequest]
    routing_notes: list[str]


def route_query(query: str, context: dict[str, Any] | None = None) -> RoutingDecision:
    """Route one task query to the relevant subset of runtime-facing tools."""

    context = context or {}
    normalized = normalize_query(query)
    routing_notes: list[str] = []
    source_preferences: list[str] = []
    tools: list[ToolRequest] = []

    explicit_component = context.get("component_hint")
    explicit_site_lookup = context.get("site_lookup")
    explicit_symbol = context.get("symbol")

    task_type = _classify_task_type(normalized)
    routing_notes.append(f"task_type={task_type}")
    if explicit_component:
        routing_notes.append("component_hint provided in context")
    if explicit_symbol:
        routing_notes.append("symbol provided in context")

    docs_needed = any(
        keyword in normalized
        for keyword in (
            "how do",
            "how does",
            "what docs",
            "policy",
            "api",
            "privacy",
            "render",
            "settings",
            "service",
            "task",
        )
    )
    code_needed = any(
        keyword in normalized
        for keyword in (
            "file",
            "symbol",
            "class",
            "function",
            "code",
            "plugin",
            "register",
            "define",
            "implement",
            "settings",
            "service",
            "privacy",
            "task",
            "render",
        )
    ) or bool(explicit_symbol)
    site_needed = any(
        keyword in normalized
        for keyword in ("render", "ui", "page", "workflow", "screen", "navigate", "moodle page")
    ) or bool(explicit_site_lookup)

    if task_type in {"admin_settings", "scheduled_task", "web_service", "privacy_metadata"}:
        docs_needed = True
        code_needed = True
    if task_type == "render_ui":
        docs_needed = True
        code_needed = True
        site_needed = True

    if docs_needed:
        tools.append(
            ToolRequest(
                tool_name="agentic_devdocs",
                reason=f"docs-oriented evidence for {task_type}",
                mode="query",
                query=query,
            )
        )
        source_preferences.append("docs")

    if code_needed:
        if explicit_symbol:
            tools.append(
                ToolRequest(
                    tool_name="agentic_indexer",
                    reason="explicit symbol context supplied",
                    mode="find-definition",
                    symbol=str(explicit_symbol),
                )
            )
        else:
            tools.append(
                ToolRequest(
                    tool_name="agentic_indexer",
                    reason=f"code-oriented evidence for {task_type}",
                    mode="build-context-bundle",
                    query=query,
                )
            )
        source_preferences.append("code")

    if site_needed:
        site_request = _site_request_for(query=query, context=context, task_type=task_type)
        tools.append(site_request)
        source_preferences.append("site")

    deduped_preferences = list(dict.fromkeys(source_preferences))
    return RoutingDecision(
        task_type=task_type,
        component_hint=explicit_component if isinstance(explicit_component, str) else None,
        source_preferences=deduped_preferences,
        tools=tools,
        routing_notes=routing_notes + [request.reason for request in tools],
    )


def _classify_task_type(normalized_query: str) -> str:
    if "settings" in normalized_query and "plugin" in normalized_query:
        return "admin_settings"
    if "scheduled task" in normalized_query or ("task" in normalized_query and "register" in normalized_query):
        return "scheduled_task"
    if "web service" in normalized_query or "external service" in normalized_query:
        return "web_service"
    if "privacy" in normalized_query:
        return "privacy_metadata"
    if any(keyword in normalized_query for keyword in ("render", "ui", "workflow", "page context", "screen")):
        return "render_ui"
    if any(keyword in normalized_query for keyword in ("symbol", "definition", "file", "class", "function")):
        return "code_lookup"
    if any(keyword in normalized_query for keyword in ("docs", "documentation", "how does moodle")):
        return "documentation"
    return "general_context"


def _site_request_for(query: str, context: dict[str, Any], task_type: str) -> ToolRequest:
    explicit = context.get("site_lookup")
    if isinstance(explicit, dict):
        mode = explicit.get("mode", "page")
        if mode == "path":
            return ToolRequest(
                tool_name="agentic_sitemap",
                reason="explicit site path context supplied",
                mode="runtime-query",
                lookup_mode="path",
                from_page=str(explicit.get("from_page", "")),
                to_page=str(explicit.get("to_page", "")),
            )
        return ToolRequest(
            tool_name="agentic_sitemap",
            reason="explicit site lookup context supplied",
            mode="runtime-query",
            lookup_mode=str(mode),
            query=str(explicit.get("query", query)),
        )

    if task_type == "render_ui":
        return ToolRequest(
            tool_name="agentic_sitemap",
            reason="render/ui tasks benefit from page-type or page-context evidence",
            mode="runtime-query",
            lookup_mode="page",
            query=query,
        )

    return ToolRequest(
        tool_name="agentic_sitemap",
        reason="site context requested by routing",
        mode="runtime-query",
        lookup_mode="page",
        query=query,
    )
