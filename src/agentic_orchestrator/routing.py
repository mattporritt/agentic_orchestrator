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
    routing_reasons: list[str]


@dataclass(frozen=True)
class AutoRoutingSignals:
    docs: bool
    code: bool
    site: bool
    reasons: list[str]


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
    routing_reasons: list[str] = []
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
        routing_reasons.append(f"known_task_family={task_type}")
    if task_type == "render_ui":
        docs_needed = True
        code_needed = True
        site_needed = True
        routing_reasons.append("known_render_ui_task")
    if explicit_symbol:
        routing_reasons.append("explicit_symbol_context")
    if explicit_site_lookup:
        routing_reasons.append("explicit_site_lookup_context")

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
        routing_reasons=routing_reasons + [request.reason for request in tools],
    )


def _auto_route(query: str, context: dict[str, Any], task_type: str, normalized: str) -> RoutingDecision:
    routing_notes: list[str] = [f"task_type={task_type}", "route_mode=auto"]
    explicit_component = context.get("component_hint")
    explicit_symbol = context.get("symbol")
    signals = _analyze_auto_routing(query=query, normalized=normalized, context=context, task_type=task_type)
    tools: list[ToolRequest] = []
    source_preferences: list[str] = []

    if signals.docs:
        tools.append(_docs_request(query=query, task_type=task_type, reason="auto selected docs"))
        source_preferences.append("docs")
    if signals.code:
        tools.append(_code_request(query=query, explicit_symbol=explicit_symbol, task_type=task_type, reason="auto selected code"))
        source_preferences.append("code")
    if signals.site:
        tools.append(_site_request_for(query=query, context=context, task_type=task_type, reason="auto selected site"))
        source_preferences.append("site")

    return RoutingDecision(
        route_mode="auto",
        task_type=task_type,
        component_hint=explicit_component if isinstance(explicit_component, str) else None,
        source_preferences=list(dict.fromkeys(source_preferences)),
        tools=tools,
        routing_notes=routing_notes + signals.reasons + [request.reason for request in tools],
        manual_tools=[],
        routing_reasons=signals.reasons + [request.reason for request in tools],
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
        routing_reasons=[f"manual_tools={','.join(manual_tools)}"] + [request.reason for request in tools],
    )


def _analyze_auto_routing(query: str, normalized: str, context: dict[str, Any], task_type: str) -> AutoRoutingSignals:
    reasons: list[str] = []
    explicit_symbol = context.get("symbol")
    explicit_site_lookup = context.get("site_lookup")

    if explicit_symbol:
        reasons.append("explicit_symbol_context")
    if explicit_site_lookup:
        reasons.append("explicit_site_lookup_context")

    conceptual_phrases = (
        "how does",
        "how should",
        "what do i need",
        "where do",
        "where are",
        "what is",
        "what page type",
        "fit with",
    )
    implementation_phrases = (
        "implement",
        "wire up",
        "register",
        "registered",
        "defined",
        "contains",
        "contain",
        "debug",
        "trace",
        "error",
        "not found",
    )
    file_phrases = ("what file", "file contains", "where is", "feature files", "language strings", "settings.php", "services.php", "tasks.php")
    docs_topics = ("api", "docs", "documentation", "guide", "privacy", "scheduled task", "web service", "admin settings", "behat", "renderer", "rendering", "output")
    code_topics = ("plugin", "file", "symbol", "class", "function", "language strings", "behat", "service", "task", "settings", "privacy", "defined", "registered")
    site_phrases = (
        "page type",
        "workflow",
        "navigate",
        "navigation",
        "path",
        "page flow",
        "screen",
        "page",
        "url",
        "dashboard",
        "course",
        "site context",
        "user preferences",
    )
    render_phrases = ("render", "rendering", "renderer", "template", "mustache", "ui pattern", "output")

    conceptual = any(phrase in normalized for phrase in conceptual_phrases)
    implementation = any(phrase in normalized for phrase in implementation_phrases)
    file_or_location = any(phrase in normalized for phrase in file_phrases)
    docs_topic = any(topic in normalized for topic in docs_topics)
    code_topic = any(topic in normalized for topic in code_topics)
    site_topic = any(phrase in normalized for phrase in site_phrases)
    render_topic = any(phrase in normalized for phrase in render_phrases)
    debug_topic = any(phrase in normalized for phrase in ("traceback", "stack trace", "exception", "undefined", "missing"))

    docs = False
    code = False
    site = False

    if task_type in {"admin_settings", "scheduled_task", "web_service", "privacy_metadata"}:
        docs = True
        code = True
        reasons.append(f"known_task_family={task_type}")

    if explicit_symbol:
        code = True

    if explicit_site_lookup:
        site = True

    if task_type == "render_ui":
        docs = True
        code = True
        reasons.append("render_ui_requires_docs_and_code")
        if site_topic or explicit_site_lookup:
            site = True
            reasons.append("page_or_site_context_present_for_render_query")

    if "behat" in normalized and "feature" in normalized:
        docs = True
        code = True
        reasons.append("behat_feature_query_needs_docs_and_code")

    if "language strings" in normalized or ("lang" in normalized and "string" in normalized):
        code = True
        reasons.append("language_string_location_is_code_oriented")

    if "page type" in normalized:
        site = True
        reasons.append("page_type_lookup_is_site_oriented")

    if site_topic and any(phrase in normalized for phrase in ("navigate", "navigation", "workflow", "path", "page flow", "page type", "screen", "page")):
        site = True
        reasons.append("workflow_or_page_context_signal")

    if site and "behat" in normalized and any(phrase in normalized for phrase in ("page", "scenario")):
        docs = True
        reasons.append("behat_page_discovery_needs_docs_and_site")

    if site and any(keyword in normalized for keyword in ("admin", "settings")) and any(
        phrase in normalized for phrase in ("page", "path", "flow", "navigation", "workflow")
    ):
        docs = True
        reasons.append("admin_or_settings_page_flow_needs_docs_and_site")

    if any(keyword in normalized for keyword in ("service", "task", "privacy", "settings")) and any(
        phrase in normalized for phrase in ("wire up", "wired up", "register", "registered", "defined")
    ):
        docs = True
        code = True
        reasons.append("subsystem_wiring_question_needs_docs_and_code")

    if render_topic and site_topic:
        docs = True
        code = True
        site = True
        reasons.append("render_plus_page_context_needs_site")

    if conceptual and docs_topic:
        docs = True
        reasons.append("conceptual_docs_signal")

    if implementation or file_or_location or debug_topic:
        if code_topic or render_topic or task_type in {"code_lookup", "general_context"}:
            code = True
            reasons.append("implementation_or_location_signal")

    if conceptual and (implementation or file_or_location) and (docs_topic or code_topic):
        docs = True
        code = True
        reasons.append("mixed_conceptual_and_implementation_signal")

    if conceptual and render_topic and not site_topic:
        docs = True
        code = True
        reasons.append("generic_render_question_uses_docs_and_code")

    if conceptual and docs_topic and not code and not site:
        docs = True
        reasons.append("docs_only_question")

    if code_topic and (file_or_location or implementation or debug_topic) and not docs and not site:
        code = True
        reasons.append("code_only_location_or_debug_question")

    if not any((docs, code, site)):
        docs = True
        code = True
        reasons.append("auto_fallback_docs_plus_code")

    deduped_reasons = list(dict.fromkeys(reasons))
    return AutoRoutingSignals(docs=docs, code=code, site=site, reasons=deduped_reasons)


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
    if any(keyword in normalized_query for keyword in ("symbol", "definition", "file", "class", "function", "language strings", "behat feature")):
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

    if "navigate" in normalize_query(query) or "workflow" in normalize_query(query):
        return ToolRequest(
            tool_name="agentic_sitemap",
            reason=reason or "workflow navigation query",
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
