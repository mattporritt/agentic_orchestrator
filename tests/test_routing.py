from __future__ import annotations

from agentic_orchestrator.routing import route_query


def test_routing_admin_settings_calls_docs_and_code() -> None:
    decision = route_query("add admin settings to a plugin")
    assert decision.task_type == "admin_settings"
    assert [tool.tool_name for tool in decision.tools] == ["agentic_devdocs", "agentic_indexer"]


def test_routing_render_query_calls_all_three_tools() -> None:
    decision = route_query("How should this render in Moodle?")
    assert decision.task_type == "render_ui"
    assert [tool.tool_name for tool in decision.tools] == [
        "agentic_devdocs",
        "agentic_indexer",
        "agentic_sitemap",
    ]


def test_routing_uses_explicit_symbol_context_for_definition_lookup() -> None:
    decision = route_query("Where is this defined?", context={"symbol": "mod_forum\\external\\discussion_exporter"})
    indexer_request = next(tool for tool in decision.tools if tool.tool_name == "agentic_indexer")
    assert indexer_request.mode == "find-definition"
    assert indexer_request.symbol == "mod_forum\\external\\discussion_exporter"
