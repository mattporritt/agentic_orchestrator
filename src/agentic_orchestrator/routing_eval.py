"""Lightweight routing evaluation for orchestrator tool selection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_orchestrator.orchestrator import OrchestratorService
from agentic_orchestrator.routing import route_query


DEFAULT_ROUTING_EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "routing_eval_v1.json"


@dataclass(frozen=True)
class RoutingEvalCase:
    id: str
    query: str
    preferred_tools: list[str]
    acceptable_tool_sets: list[list[str]]
    disallowed_tools: list[str]
    notes: list[str]
    context: dict[str, Any]
    compare_modes: bool = False


def load_routing_eval_cases(path: str | Path | None = None) -> list[RoutingEvalCase]:
    """Load routing evaluation cases from the default or provided JSON fixture."""

    fixture_path = Path(path) if path else DEFAULT_ROUTING_EVAL_PATH
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = []
    for item in payload["cases"]:
        cases.append(
            RoutingEvalCase(
                id=item["id"],
                query=item["query"],
                preferred_tools=list(item.get("preferred_tools", [])),
                acceptable_tool_sets=[list(group) for group in item.get("acceptable_tool_sets", [])],
                disallowed_tools=list(item.get("disallowed_tools", [])),
                notes=list(item.get("notes", [])),
                context=dict(item.get("context", {})),
                compare_modes=bool(item.get("compare_modes", False)),
            )
        )
    return cases


def grade_routing_case(case: RoutingEvalCase, selected_tools: list[str]) -> dict[str, str]:
    """Grade one selected tool set against the deterministic routing semantics."""

    selected = set(selected_tools)
    preferred = set(case.preferred_tools)
    acceptable_sets = [set(group) for group in case.acceptable_tool_sets]
    disallowed = set(case.disallowed_tools)

    if selected == preferred:
        return {"status": "CORRECT", "reason": "selected tools exactly matched the preferred tool set"}
    if any(selected == acceptable for acceptable in acceptable_sets):
        return {"status": "ACCEPTABLE", "reason": "selected tools matched an explicitly acceptable tool set"}
    if disallowed & selected:
        if preferred <= selected or any(acceptable <= selected for acceptable in acceptable_sets):
            return {"status": "OVERCALLED", "reason": "selected tools included a disallowed extra tool"}
        return {"status": "WRONG", "reason": "selected tools included a disallowed tool without matching a useful baseline"}
    if preferred < selected or any(acceptable < selected for acceptable in acceptable_sets):
        return {"status": "OVERCALLED", "reason": "selected tools were a useful superset of the expected set"}
    if selected < preferred or any(selected < acceptable for acceptable in acceptable_sets):
        return {"status": "UNDERCALLED", "reason": "selected tools omitted a tool expected for this case"}
    return {"status": "WRONG", "reason": "selected tools did not match any preferred or acceptable routing pattern"}


def evaluate_auto_routing(
    service: OrchestratorService,
    *,
    cases: list[RoutingEvalCase] | None = None,
) -> dict[str, Any]:
    """Evaluate auto routing by executing the orchestrator and grading tool selection."""

    loaded_cases = cases or load_routing_eval_cases()
    results: list[dict[str, Any]] = []
    counts = {"CORRECT": 0, "ACCEPTABLE": 0, "OVERCALLED": 0, "UNDERCALLED": 0, "WRONG": 0}

    for case in loaded_cases:
        payload = service.query(query=case.query, context=case.context, route_mode="auto")
        selected_tools = [item["tool"] for item in payload["results"][0]["diagnostics"]["tools_called"]]
        grade = grade_routing_case(case, selected_tools)
        payload["results"][0]["diagnostics"]["routing_eval_status"] = grade["status"]
        payload["results"][0]["diagnostics"]["routing_eval_reason"] = grade["reason"]
        payload["results"][0]["diagnostics"]["routing_eval_case_id"] = case.id
        counts[grade["status"]] += 1
        results.append(
            {
                "case_id": case.id,
                "query": case.query,
                "preferred_tools": case.preferred_tools,
                "acceptable_tool_sets": case.acceptable_tool_sets,
                "disallowed_tools": case.disallowed_tools,
                "selected_tools": selected_tools,
                "status": grade["status"],
                "reason": grade["reason"],
                "notes": case.notes,
                "payload": payload,
            }
        )

    return {"cases": results, "summary": counts}


def compare_modes_for_case(case: RoutingEvalCase) -> dict[str, Any]:
    """Compare tool selection across task, auto, and manual modes for one case."""

    task_decision = route_query(case.query, context=case.context, route_mode="task")
    auto_decision = route_query(case.query, context=case.context, route_mode="auto")
    manual_decision = route_query(case.query, context=case.context, route_mode="manual", manual_tools=case.preferred_tools)
    return {
        "case_id": case.id,
        "query": case.query,
        "task_tools": [item.tool_name for item in task_decision.tools],
        "auto_tools": [item.tool_name for item in auto_decision.tools],
        "manual_tools": [item.tool_name for item in manual_decision.tools],
    }


def render_routing_eval_text(evaluation: dict[str, Any]) -> str:
    """Render a compact text summary of routing eval results."""

    lines = ["Routing Eval", ""]
    summary = evaluation["summary"]
    lines.append(
        "Summary: "
        + ", ".join(f"{key.lower()}={summary[key]}" for key in ("CORRECT", "ACCEPTABLE", "OVERCALLED", "UNDERCALLED", "WRONG"))
    )
    lines.append("")
    for case in evaluation["cases"]:
        lines.append(f"- {case['case_id']}: {case['status']} -> {', '.join(case['selected_tools'])}")
        lines.append(f"  preferred: {', '.join(case['preferred_tools'])}")
        if case["acceptable_tool_sets"]:
            acceptable = ["{" + ", ".join(group) + "}" for group in case["acceptable_tool_sets"]]
            lines.append(f"  acceptable: {', '.join(acceptable)}")
        if case["disallowed_tools"]:
            lines.append(f"  disallowed: {', '.join(case['disallowed_tools'])}")
        lines.append(f"  reason: {case['reason']}")
    return "\n".join(lines) + "\n"
