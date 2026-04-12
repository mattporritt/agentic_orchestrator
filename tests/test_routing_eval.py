from __future__ import annotations

import json
from pathlib import Path

from agentic_orchestrator.routing_eval import (
    RoutingEvalCase,
    compare_modes_for_case,
    grade_routing_case,
    load_routing_eval_cases,
)


def test_load_routing_eval_cases_from_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "routing_eval.json"
    fixture.write_text(
        json.dumps(
            {
                "version": "v1",
                "cases": [
                    {
                        "id": "one",
                        "query": "Where do settings go?",
                        "preferred_tools": ["agentic_devdocs", "agentic_indexer"],
                        "acceptable_tool_sets": [["agentic_devdocs"]],
                        "disallowed_tools": ["agentic_sitemap"],
                        "notes": ["example"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cases = load_routing_eval_cases(fixture)
    assert len(cases) == 1
    assert cases[0].id == "one"
    assert cases[0].acceptable_tool_sets == [["agentic_devdocs"]]


def test_grade_routing_case_semantics() -> None:
    case = RoutingEvalCase(
        id="test",
        query="query",
        preferred_tools=["agentic_devdocs", "agentic_indexer"],
        acceptable_tool_sets=[["agentic_devdocs"]],
        disallowed_tools=["agentic_sitemap"],
        notes=[],
        context={},
    )
    assert grade_routing_case(case, ["agentic_devdocs", "agentic_indexer"])["status"] == "CORRECT"
    assert grade_routing_case(case, ["agentic_devdocs"])["status"] == "ACCEPTABLE"
    assert grade_routing_case(case, ["agentic_devdocs", "agentic_indexer", "agentic_sitemap"])["status"] == "OVERCALLED"
    assert grade_routing_case(case, ["agentic_indexer"])["status"] == "UNDERCALLED"
    assert grade_routing_case(case, ["agentic_sitemap"])["status"] == "WRONG"


def test_compare_modes_for_case_returns_mode_tool_sets() -> None:
    case = RoutingEvalCase(
        id="page_type",
        query="What page type is this in Moodle?",
        preferred_tools=["agentic_sitemap"],
        acceptable_tool_sets=[],
        disallowed_tools=["agentic_indexer"],
        notes=[],
        context={},
        compare_modes=True,
    )
    comparison = compare_modes_for_case(case)
    assert comparison["case_id"] == "page_type"
    assert comparison["auto_tools"] == ["agentic_sitemap"]
    assert comparison["manual_tools"] == ["agentic_sitemap"]
