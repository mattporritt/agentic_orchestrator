from __future__ import annotations

import pytest

from agentic_orchestrator.errors import ConfigurationError
from agentic_orchestrator.routing import route_query


def test_task_routing_preserves_admin_settings_route() -> None:
    decision = route_query("add admin settings to a plugin", route_mode="task")
    assert decision.route_mode == "task"
    assert decision.task_type == "admin_settings"
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_indexer"]


def test_auto_routing_picks_docs_and_code_for_service_wiring_question() -> None:
    decision = route_query("How should I wire up a service and where is it defined?", route_mode="auto")
    assert decision.route_mode == "auto"
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_indexer"]


def test_auto_routing_avoids_sitemap_for_generic_render_question() -> None:
    decision = route_query("How should this render in Moodle?", route_mode="auto")
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_indexer"]


def test_auto_routing_can_choose_site_only_for_page_type_query() -> None:
    decision = route_query("What page type is this in Moodle?", route_mode="auto")
    assert [tool.tool_name for tool in decision.tools] == ["agentic_sitemap"]


def test_auto_routing_fixes_navigation_path_workflow_case() -> None:
    decision = route_query("How do I make sense of this navigation path in Moodle?", route_mode="auto")
    assert [tool.tool_name for tool in decision.tools] == ["agentic_sitemap"]
    assert "workflow_or_page_context_signal" in decision.routing_reasons


def test_auto_routing_improves_service_wiring_to_docs_and_code() -> None:
    decision = route_query("Where is this service actually wired up?", route_mode="auto")
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_indexer"]
    assert "subsystem_wiring_question_needs_docs_and_code" in decision.routing_reasons


def test_auto_routing_improves_ambiguous_admin_page_flow_to_docs_and_site() -> None:
    decision = route_query("This admin page looks wrong, where should I start?", route_mode="auto")
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_sitemap"]
    assert "admin_or_settings_page_flow_needs_docs_and_site" in decision.routing_reasons


def test_auto_routing_improves_ambiguous_behat_page_discovery_to_docs_and_site() -> None:
    decision = route_query("Where should I look if a Behat scenario cannot find the page?", route_mode="auto")
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_sitemap"]
    assert "behat_page_discovery_needs_docs_and_site" in decision.routing_reasons


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
