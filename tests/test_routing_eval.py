# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

from __future__ import annotations

import json
from pathlib import Path

from agentic_orchestrator.routing_eval import (
    RoutingEvalCase,
    evaluate_auto_routing,
    compare_modes_for_case,
    grade_routing_case,
    load_routing_eval_cases,
    render_routing_eval_text,
)
from agentic_orchestrator.orchestrator import OrchestratorService
from tests.test_orchestrator import _config, _runner


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
                        "query_style": "ambiguous",
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
    assert cases[0].query_style == "ambiguous"
    assert cases[0].acceptable_tool_sets == [["agentic_devdocs"]]


def test_grade_routing_case_semantics() -> None:
    case = RoutingEvalCase(
        id="test",
        query="query",
        query_style="debugging",
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
        query_style="workflow",
        preferred_tools=["agentic_sitemap"],
        acceptable_tool_sets=[],
        disallowed_tools=["agentic_indexer"],
        notes=[],
        context={},
        compare_modes=True,
    )
    comparison = compare_modes_for_case(case)
    assert comparison["case_id"] == "page_type"
    assert comparison["query_style"] == "workflow"
    assert comparison["auto_tools"] == ["agentic_sitemap"]
    assert comparison["manual_tools"] == ["agentic_sitemap"]


def test_render_routing_eval_text_includes_style_breakdown() -> None:
    evaluation = {
        "summary": {"CORRECT": 1, "ACCEPTABLE": 1, "OVERCALLED": 0, "UNDERCALLED": 0, "WRONG": 0},
        "by_query_style": {
            "debugging": {"CORRECT": 1, "ACCEPTABLE": 0, "OVERCALLED": 0, "UNDERCALLED": 0, "WRONG": 0},
            "ambiguous": {"CORRECT": 0, "ACCEPTABLE": 1, "OVERCALLED": 0, "UNDERCALLED": 0, "WRONG": 0},
        },
        "cases": [
            {
                "case_id": "one",
                "query_style": "debugging",
                "selected_tools": ["agentic_indexer"],
                "preferred_tools": ["agentic_indexer"],
                "acceptable_tool_sets": [],
                "disallowed_tools": [],
                "status": "CORRECT",
                "reason": "ok",
            }
        ],
    }
    text = render_routing_eval_text(evaluation)
    assert "By query style:" in text
    assert "debugging: correct=1" in text
    assert "[debugging]" in text


def test_evaluate_auto_routing_exposes_eval_expectations_in_diagnostics() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    case = RoutingEvalCase(
        id="navigation_path_messy",
        query="How do I make sense of this navigation path in Moodle?",
        query_style="workflow",
        preferred_tools=["agentic_sitemap"],
        acceptable_tool_sets=[["agentic_devdocs", "agentic_sitemap"]],
        disallowed_tools=["agentic_indexer"],
        notes=[],
        context={},
    )
    evaluation = evaluate_auto_routing(service, cases=[case])
    result = evaluation["cases"][0]
    diagnostics = result["payload"]["results"][0]["diagnostics"]
    assert result["status"] == "CORRECT"
    assert diagnostics["routing_eval_preferred_tools"] == ["agentic_sitemap"]
    assert diagnostics["routing_eval_acceptable_tool_sets"] == [["agentic_devdocs", "agentic_sitemap"]]
    assert diagnostics["routing_eval_status"] == "CORRECT"
