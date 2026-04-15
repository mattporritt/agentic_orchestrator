from __future__ import annotations

import json
from pathlib import Path

from agentic_orchestrator.debug_eval import evaluate_debug_routes, load_debug_eval_cases, render_debug_eval_text
from agentic_orchestrator.orchestrator import OrchestratorService
from tests.test_orchestrator import _config, _runner


def test_load_debug_eval_cases_from_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "debug_eval.json"
    fixture.write_text(
        json.dumps(
            {
                "version": "v1",
                "cases": [
                    {
                        "id": "plan_phpunit",
                        "query": "plan debug for this PHPUnit selector mod_assign\\tests\\grading_test::test_grade_submission",
                        "expected_tools": ["agentic_debug"],
                        "expected_intent": "plan_phpunit",
                        "expected_execution_mode": "safe",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cases = load_debug_eval_cases(fixture)
    assert len(cases) == 1
    assert cases[0].expected_intent == "plan_phpunit"


def test_evaluate_debug_routes_checks_intent_and_execution_boundary() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    evaluation = evaluate_debug_routes(service)
    assert evaluation["summary"]["WRONG"] == 0
    assert evaluation["summary"]["CORRECT"] >= 5
    first = evaluation["cases"][0]
    assert first["selected_tools"] == ["agentic_debug"]
    assert first["payload"]["results"][0]["content"]["debug_results"]


def test_render_debug_eval_text_includes_summary() -> None:
    text = render_debug_eval_text(
        {
            "summary": {"CORRECT": 2, "WRONG": 1},
            "cases": [
                {
                    "case_id": "interpret_debug_session",
                    "status": "CORRECT",
                    "selected_tools": ["agentic_debug"],
                    "debug_intent": "interpret_session",
                    "debug_execution_mode": "safe",
                }
            ],
        }
    )
    assert "Summary: correct=2, wrong=1" in text
    assert "interpret_session" in text
