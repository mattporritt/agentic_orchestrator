"""Conservative evaluation slice for debugger routing and grouping."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_orchestrator.config import resolve_repo_root
from agentic_orchestrator.orchestrator import OrchestratorService


@dataclass(frozen=True)
class DebugEvalCase:
    id: str
    query: str
    expected_tools: list[str]
    expected_intent: str
    expected_execution_mode: str
    notes: list[str]
    context: dict[str, Any]


def load_debug_eval_cases(path: Path | None = None) -> list[DebugEvalCase]:
    fixture_path = path or (resolve_repo_root() / "evals" / "debug_eval_v1.json")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return [
        DebugEvalCase(
            id=item["id"],
            query=item["query"],
            expected_tools=item["expected_tools"],
            expected_intent=item["expected_intent"],
            expected_execution_mode=item["expected_execution_mode"],
            notes=item.get("notes", []),
            context=item.get("context", {}),
        )
        for item in payload["cases"]
    ]


def evaluate_debug_routes(service: OrchestratorService, *, cases: list[DebugEvalCase] | None = None) -> dict[str, Any]:
    active_cases = cases or load_debug_eval_cases()
    results: list[dict[str, Any]] = []
    summary = {"CORRECT": 0, "WRONG": 0}
    for case in active_cases:
        payload = service.query(query=case.query, context=case.context, route_mode="task")
        diagnostics = payload["results"][0]["diagnostics"]
        selected_tools = diagnostics["selected_tools"]
        debug_intent = diagnostics.get("debug_intent")
        execution_mode = diagnostics.get("debug_execution_mode")
        debug_results = payload["results"][0]["content"]["debug_results"]
        correct = (
            selected_tools == case.expected_tools
            and debug_intent == case.expected_intent
            and execution_mode == case.expected_execution_mode
            and bool(debug_results)
        )
        status = "CORRECT" if correct else "WRONG"
        summary[status] += 1
        results.append(
            {
                "case_id": case.id,
                "query": case.query,
                "expected_tools": case.expected_tools,
                "selected_tools": selected_tools,
                "expected_intent": case.expected_intent,
                "debug_intent": debug_intent,
                "expected_execution_mode": case.expected_execution_mode,
                "debug_execution_mode": execution_mode,
                "status": status,
                "notes": case.notes,
                "payload": payload,
            }
        )
    return {"summary": summary, "cases": results}


def render_debug_eval_text(evaluation: dict[str, Any]) -> str:
    lines = [
        "Debug Eval",
        "",
        f"Summary: correct={evaluation['summary']['CORRECT']}, wrong={evaluation['summary']['WRONG']}",
        "",
    ]
    for case in evaluation["cases"]:
        lines.append(
            f"- {case['case_id']}: {case['status']} | selected={','.join(case['selected_tools'])} | intent={case['debug_intent']} | mode={case['debug_execution_mode']}"
        )
    return "\n".join(lines) + "\n"
