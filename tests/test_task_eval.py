from __future__ import annotations

import json
from pathlib import Path

from agentic_orchestrator.orchestrator import OrchestratorService
from agentic_orchestrator.task_eval import (
    TaskEvalCase,
    TaskSignalExpectation,
    evaluate_task_outputs,
    grade_task_case,
    load_task_eval_cases,
    render_task_eval_text,
)
from tests.test_orchestrator import _config, _runner


def test_load_task_eval_cases_from_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "task_eval.json"
    fixture.write_text(
        json.dumps(
            {
                "version": "v1",
                "cases": [
                    {
                        "id": "admin",
                        "query": "add admin settings to a plugin",
                        "route_mode": "task",
                        "expected_tools": ["agentic_devdocs", "agentic_indexer"],
                        "required_signals": [{"label": "settings file", "kind": "path_contains", "value": "settings.php"}],
                        "notes": ["example"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cases = load_task_eval_cases(fixture)
    assert len(cases) == 1
    assert cases[0].route_mode == "task"
    assert cases[0].required_signals[0].label == "settings file"


def test_grade_task_case_semantics() -> None:
    assert grade_task_case(
        expected_tools=["agentic_devdocs", "agentic_indexer"],
        selected_tools=["agentic_devdocs", "agentic_indexer"],
        missing_signals=[],
        thinness_flags=[],
        noise_flags=[],
    )["status"] == "COMPLETE"
    assert grade_task_case(
        expected_tools=["agentic_devdocs", "agentic_indexer"],
        selected_tools=["agentic_devdocs", "agentic_indexer"],
        missing_signals=["services php"],
        thinness_flags=[],
        noise_flags=[],
    )["status"] == "PARTIAL"
    assert grade_task_case(
        expected_tools=["agentic_devdocs", "agentic_indexer"],
        selected_tools=["agentic_devdocs"],
        missing_signals=[],
        thinness_flags=[],
        noise_flags=[],
    )["status"] == "INSUFFICIENT"


def test_evaluate_task_outputs_reports_signal_coverage_and_noise() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    case = TaskEvalCase(
        id="admin",
        query="add admin settings to a plugin",
        route_mode="task",
        expected_tools=["agentic_devdocs", "agentic_indexer"],
        required_signals=[
            TaskSignalExpectation(label="admin docs path", kind="docs_path_contains", value="docs/example.md"),
            TaskSignalExpectation(label="settings file", kind="path_contains", value="settings.php"),
            TaskSignalExpectation(label="settings next step", kind="next_step_contains", value="settings.php"),
        ],
        notes=[],
        context={},
    )
    evaluation = evaluate_task_outputs(service, cases=[case])
    result = evaluation["cases"][0]
    diagnostics = result["payload"]["results"][0]["diagnostics"]
    assert result["status"] == "COMPLETE"
    assert "settings file" in result["key_signals_present"]
    assert result["missing_signals"] == []
    assert result["noise_flags"] == []
    assert diagnostics["task_eval_status"] == "COMPLETE"
    assert diagnostics["key_signals_present"]


def test_render_task_eval_text_includes_usefulness_summary() -> None:
    text = render_task_eval_text(
        {
            "summary": {"COMPLETE": 1, "PARTIAL": 1, "INSUFFICIENT": 0},
            "cases": [
                {
                    "case_id": "admin",
                    "selected_tools": ["agentic_devdocs", "agentic_indexer"],
                    "status": "PARTIAL",
                    "key_signals_present": ["admin docs path"],
                    "missing_signals": ["settings file"],
                    "thinness_flags": [],
                    "noise_flags": [],
                    "reason": "usable but thin",
                }
            ],
        }
    )
    assert "Summary: complete=1, partial=1, insufficient=0" in text
    assert "missing: settings file" in text
