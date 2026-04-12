from __future__ import annotations

import pytest

from agentic_orchestrator.errors import ConfigurationError
from agentic_orchestrator.routing import route_query


def test_task_routing_preserves_admin_settings_route() -> None:
    decision = route_query("add admin settings to a plugin", route_mode="task")
    assert decision.route_mode == "task"
    assert decision.task_type == "admin_settings"
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_indexer"]


def test_auto_routing_can_choose_single_tool_for_docs_query() -> None:
    decision = route_query("Where are the docs for the output API?", route_mode="auto")
    assert decision.route_mode == "auto"
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs"]


def test_manual_routing_uses_selected_tools_only() -> None:
    decision = route_query("How should this render in Moodle?", route_mode="manual", manual_tools=["agentic_indexer", "agentic_sitemap"])
    assert decision.route_mode == "manual"
    assert [tool.tool_name for tool in decision.tools] == ["agentic_indexer", "agentic_sitemap"]


def test_manual_routing_requires_selected_tools() -> None:
    with pytest.raises(ConfigurationError):
        route_query("anything", route_mode="manual", manual_tools=[])


def test_task_routing_uses_explicit_symbol_context_for_definition_lookup() -> None:
    decision = route_query(
        "Where is this defined?",
        route_mode="task",
        context={"symbol": "mod_forum\\external\\discussion_exporter"},
    )
    indexer_request = next(tool for tool in decision.tools if tool.tool_name == "agentic_indexer")
    assert indexer_request.mode == "find-definition"
    assert indexer_request.symbol == "mod_forum\\external\\discussion_exporter"
