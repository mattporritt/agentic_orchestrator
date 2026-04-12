"""Explicit routing modes for the thin orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_orchestrator.contract import normalize_query
from agentic_orchestrator.errors import ConfigurationError


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
    route_mode: str
    task_type: str
    component_hint: str | None
    source_preferences: list[str]
    tools: list[ToolRequest]
    routing_notes: list[str]
    manual_tools: list[str]


def route_query(
    query: str,
    *,
    context: dict[str, Any] | None = None,
    route_mode: str = "task",
    manual_tools: list[str] | None = None,
) -> RoutingDecision:
    """Route one task query to the relevant subset of runtime-facing tools."""

    context = context or {}
    manual_tools = list(manual_tools or [])
    normalized = normalize_query(query)
    task_type = _classify_task_type(normalized)
    if route_mode not in {"task", "auto", "manual"}:
        raise ConfigurationError(f"Unsupported route mode '{route_mode}'.")
    if route_mode == "manual":
        if not manual_tools:
            raise ConfigurationError("Manual route mode requires at least one selected tool.")
        return _manual_route(query=query, context=context, task_type=task_type, manual_tools=manual_tools)
    if route_mode == "auto":
        return _auto_route(query=query, context=context, task_type=task_type, normalized=normalized)
    return _task_route(query=query, context=context, task_type=task_type, normalized=normalized)


def _task_route(query: str, context: dict[str, Any], task_type: str, normalized: str) -> RoutingDecision:
    routing_notes: list[str] = [f"task_type={task_type}", "route_mode=task"]
    explicit_component = context.get("component_hint")
    explicit_site_lookup = context.get("site_lookup")
    explicit_symbol = context.get("symbol")
    tools: list[ToolRequest] = []
    source_preferences: list[str] = []

    docs_needed = any(
        keyword in normalized
        for keyword in ("how do", "how does", "what docs", "policy", "api", "privacy", "render", "settings", "service", "task")
    )
    code_needed = any(
        keyword in normalized
        for keyword in ("file", "symbol", "class", "function", "code", "plugin", "register", "define", "implement", "settings", "service", "privacy", "task", "render")
    ) or bool(explicit_symbol)
    site_needed = any(
        keyword in normalized for keyword in ("render", "ui", "page", "workflow", "screen", "navigate", "moodle page")
    ) or bool(explicit_site_lookup)

    if task_type in {"admin_settings", "scheduled_task", "web_service", "privacy_metadata"}:
        docs_needed = True
        code_needed = True
    if task_type == "render_ui":
        docs_needed = True
        code_needed = True
        site_needed = True

    if docs_needed:
        tools.append(_docs_request(query=query, task_type=task_type))
        source_preferences.append("docs")
    if code_needed:
        tools.append(_code_request(query=query, explicit_symbol=explicit_symbol, task_type=task_type))
        source_preferences.append("code")
    if site_needed:
        tools.append(_site_request_for(query=query, context=context, task_type=task_type))
        source_preferences.append("site")

    return RoutingDecision(
        route_mode="task",
        task_type=task_type,
        component_hint=explicit_component if isinstance(explicit_component, str) else None,
        source_preferences=list(dict.fromkeys(source_preferences)),
        tools=tools,
        routing_notes=routing_notes + [request.reason for request in tools],
        manual_tools=[],
    )


def _auto_route(query: str, context: dict[str, Any], task_type: str, normalized: str) -> RoutingDecision:
    routing_notes: list[str] = [f"task_type={task_type}", "route_mode=auto"]
    explicit_component = context.get("component_hint")
    explicit_symbol = context.get("symbol")
    explicit_site_lookup = context.get("site_lookup")
    tools: list[ToolRequest] = []
    source_preferences: list[str] = []

    if explicit_symbol:
        tools.append(_code_request(query=query, explicit_symbol=explicit_symbol, task_type=task_type))
        source_preferences.append("code")

    docs_signals = ("docs", "documentation", "guide", "policy", "api", "how do", "how does")
    code_signals = ("file", "symbol", "class", "function", "implementation", "code", "plugin", "define", "register")
    site_signals = ("ui", "page", "workflow", "screen", "render", "navigation", "dashboard", "course")

    docs_hit = any(signal in normalized for signal in docs_signals)
    code_hit = any(signal in normalized for signal in code_signals)
    site_hit = any(signal in normalized for signal in site_signals) or bool(explicit_site_lookup)

    if task_type in {"admin_settings", "scheduled_task", "web_service", "privacy_metadata"}:
        docs_hit = True
        code_hit = True
    if task_type == "render_ui":
        docs_hit = True
        code_hit = True
        site_hit = True
    if not any((docs_hit, code_hit, site_hit)):
        docs_hit = True
        code_hit = True
        routing_notes.append("auto fallback selected docs+code for general context")

    if docs_hit:
        tools.append(_docs_request(query=query, task_type=task_type))
        source_preferences.append("docs")
    if code_hit and not explicit_symbol:
        tools.append(_code_request(query=query, explicit_symbol=None, task_type=task_type))
        source_preferences.append("code")
    if site_hit:
        tools.append(_site_request_for(query=query, context=context, task_type=task_type))
        source_preferences.append("site")

    return RoutingDecision(
        route_mode="auto",
        task_type=task_type,
        component_hint=explicit_component if isinstance(explicit_component, str) else None,
        source_preferences=list(dict.fromkeys(source_preferences)),
        tools=tools,
        routing_notes=routing_notes + [request.reason for request in tools],
        manual_tools=[],
    )


def _manual_route(query: str, context: dict[str, Any], task_type: str, manual_tools: list[str]) -> RoutingDecision:
    explicit_component = context.get("component_hint")
    explicit_symbol = context.get("symbol")
    tools: list[ToolRequest] = []
    source_preferences: list[str] = []
    for tool_name in manual_tools:
        if tool_name == "agentic_devdocs":
            tools.append(_docs_request(query=query, task_type=task_type, reason="manual tool selection"))
            source_preferences.append("docs")
        elif tool_name == "agentic_indexer":
            tools.append(_code_request(query=query, explicit_symbol=explicit_symbol, task_type=task_type, reason="manual tool selection"))
            source_preferences.append("code")
        elif tool_name == "agentic_sitemap":
            tools.append(_site_request_for(query=query, context=context, task_type=task_type, reason="manual tool selection"))
            source_preferences.append("site")
        else:
            raise ConfigurationError(f"Unsupported manual tool selection '{tool_name}'.")

    return RoutingDecision(
        route_mode="manual",
        task_type=task_type,
        component_hint=explicit_component if isinstance(explicit_component, str) else None,
        source_preferences=source_preferences,
        tools=tools,
        routing_notes=[f"task_type={task_type}", "route_mode=manual", f"manual_tools={','.join(manual_tools)}"] + [request.reason for request in tools],
        manual_tools=list(manual_tools),
    )


def _docs_request(query: str, task_type: str, reason: str | None = None) -> ToolRequest:
    return ToolRequest(
        tool_name="agentic_devdocs",
        reason=reason or f"docs-oriented evidence for {task_type}",
        mode="query",
        query=query,
    )


def _code_request(query: str, explicit_symbol: Any, task_type: str, reason: str | None = None) -> ToolRequest:
    if explicit_symbol:
        return ToolRequest(
            tool_name="agentic_indexer",
            reason=reason or "explicit symbol context supplied",
            mode="find-definition",
            symbol=str(explicit_symbol),
        )
    return ToolRequest(
        tool_name="agentic_indexer",
        reason=reason or f"code-oriented evidence for {task_type}",
        mode="build-context-bundle",
        query=query,
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


def _site_request_for(query: str, context: dict[str, Any], task_type: str, reason: str | None = None) -> ToolRequest:
    explicit = context.get("site_lookup")
    if isinstance(explicit, dict):
        mode = explicit.get("mode", "page")
        if mode == "path":
            return ToolRequest(
                tool_name="agentic_sitemap",
                reason=reason or "explicit site path context supplied",
                mode="runtime-query",
                lookup_mode="path",
                from_page=str(explicit.get("from_page", "")),
                to_page=str(explicit.get("to_page", "")),
            )
        return ToolRequest(
            tool_name="agentic_sitemap",
            reason=reason or "explicit site lookup context supplied",
            mode="runtime-query",
            lookup_mode=str(mode),
            query=str(explicit.get("query", query)),
        )

    if task_type == "render_ui":
        return ToolRequest(
            tool_name="agentic_sitemap",
            reason=reason or "render/ui tasks benefit from page-type or page-context evidence",
            mode="runtime-query",
            lookup_mode="page_type",
            query="dashboard",
        )

    return ToolRequest(
        tool_name="agentic_sitemap",
        reason=reason or "site context requested by routing",
        mode="runtime-query",
        lookup_mode="page",
        query=query,
    )
