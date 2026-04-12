"""Task-level evaluation for merged orchestrator context usefulness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_orchestrator.orchestrator import OrchestratorService


DEFAULT_TASK_EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "task_eval_v1.json"
TASK_EVAL_STATUSES = ("COMPLETE", "PARTIAL", "INSUFFICIENT")


@dataclass(frozen=True)
class TaskSignalExpectation:
    label: str
    kind: str
    value: str


@dataclass(frozen=True)
class TaskEvalCase:
    id: str
    query: str
    route_mode: str
    expected_tools: list[str]
    required_signals: list[TaskSignalExpectation]
    notes: list[str]
    context: dict[str, Any]


def load_task_eval_cases(path: str | Path | None = None) -> list[TaskEvalCase]:
    fixture_path = Path(path) if path else DEFAULT_TASK_EVAL_PATH
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases: list[TaskEvalCase] = []
    for item in payload["cases"]:
        cases.append(
            TaskEvalCase(
                id=item["id"],
                query=item["query"],
                route_mode=str(item.get("route_mode", "task")),
                expected_tools=list(item.get("expected_tools", [])),
                required_signals=[
                    TaskSignalExpectation(
                        label=str(signal["label"]),
                        kind=str(signal["kind"]),
                        value=str(signal["value"]),
                    )
                    for signal in item.get("required_signals", [])
                ],
                notes=list(item.get("notes", [])),
                context=dict(item.get("context", {})),
            )
        )
    return cases


def evaluate_task_outputs(
    service: OrchestratorService,
    *,
    cases: list[TaskEvalCase] | None = None,
) -> dict[str, Any]:
    loaded_cases = cases or load_task_eval_cases()
    counts = {status: 0 for status in TASK_EVAL_STATUSES}
    results: list[dict[str, Any]] = []

    for case in loaded_cases:
        payload = service.query(query=case.query, context=case.context, route_mode=case.route_mode)
        result = payload["results"][0]
        selected_tools = [item["tool"] for item in result["diagnostics"]["tools_called"]]
        present_labels: list[str] = []
        missing_labels: list[str] = []
        for signal in case.required_signals:
            if _signal_present(result, signal):
                present_labels.append(signal.label)
            else:
                missing_labels.append(signal.label)
        thinness_flags = _thinness_flags(case, result)
        noise_flags = _noise_flags(result)
        grade = grade_task_case(
            expected_tools=case.expected_tools,
            selected_tools=selected_tools,
            missing_signals=missing_labels,
            thinness_flags=thinness_flags,
            noise_flags=noise_flags,
        )
        result["diagnostics"]["task_eval_status"] = grade["status"]
        result["diagnostics"]["task_eval_reason"] = grade["reason"]
        result["diagnostics"]["task_eval_case_id"] = case.id
        result["diagnostics"]["key_signals_present"] = present_labels
        result["diagnostics"]["missing_signals"] = missing_labels
        result["diagnostics"]["noise_flags"] = noise_flags
        counts[grade["status"]] += 1
        results.append(
            {
                "case_id": case.id,
                "query": case.query,
                "route_mode": case.route_mode,
                "expected_tools": case.expected_tools,
                "selected_tools": selected_tools,
                "status": grade["status"],
                "reason": grade["reason"],
                "key_signals_present": present_labels,
                "missing_signals": missing_labels,
                "thinness_flags": thinness_flags,
                "noise_flags": noise_flags,
                "assembly_notes": list(result["diagnostics"].get("assembly_notes", [])),
                "notes": case.notes,
                "payload": payload,
            }
        )

    return {"cases": results, "summary": counts}


def grade_task_case(
    *,
    expected_tools: list[str],
    selected_tools: list[str],
    missing_signals: list[str],
    thinness_flags: list[str],
    noise_flags: list[str],
) -> dict[str, str]:
    missing_tools = [tool for tool in expected_tools if tool not in selected_tools]
    if missing_tools:
        return {"status": "INSUFFICIENT", "reason": f"missing expected tools: {', '.join(missing_tools)}"}
    if "no_key_signals" in thinness_flags or len(missing_signals) >= 2:
        return {"status": "INSUFFICIENT", "reason": "merged context is missing too many required task signals"}
    if missing_signals or thinness_flags or noise_flags:
        return {"status": "PARTIAL", "reason": "merged context is usable but still thin, noisy, or missing a key signal"}
    return {"status": "COMPLETE", "reason": "merged context included the expected tool contributions and required task signals"}


def render_task_eval_text(evaluation: dict[str, Any]) -> str:
    lines = ["Task Eval", ""]
    summary = evaluation["summary"]
    lines.append("Summary: " + ", ".join(f"{key.lower()}={summary[key]}" for key in TASK_EVAL_STATUSES))
    lines.append("")
    for case in evaluation["cases"]:
        lines.append(f"- {case['case_id']}: {case['status']} -> {', '.join(case['selected_tools'])}")
        lines.append(f"  present: {', '.join(case['key_signals_present']) or '(none)'}")
        if case["missing_signals"]:
            lines.append(f"  missing: {', '.join(case['missing_signals'])}")
        if case["thinness_flags"]:
            lines.append(f"  thinness: {', '.join(case['thinness_flags'])}")
        if case["noise_flags"]:
            lines.append(f"  noise: {', '.join(case['noise_flags'])}")
        lines.append(f"  reason: {case['reason']}")
    return "\n".join(lines) + "\n"


def _signal_present(result: dict[str, Any], signal: TaskSignalExpectation) -> bool:
    content = result["content"]
    value = signal.value
    if signal.kind == "docs_path_contains":
        return any(value in str(item.get("source", {}).get("path", "")) for item in content["docs_results"])
    if signal.kind == "path_contains":
        for haystack in _collect_paths(result):
            if value in haystack:
                return True
        return False
    if signal.kind == "next_step_contains":
        return any(value in str(step.get("value", "")) for step in content.get("suggested_next_steps", []))
    if signal.kind == "site_page_type":
        return any(value == str(item.get("content", {}).get("page_type", "")) for item in content["site_results"])
    raise ValueError(f"Unsupported task signal kind '{signal.kind}'.")


def _collect_paths(result: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    content = result["content"]
    for group_name in ("docs_results", "code_results", "site_results"):
        for item in content.get(group_name, []):
            source_path = item.get("source", {}).get("path")
            if isinstance(source_path, str) and source_path:
                paths.append(source_path)
            body = item.get("content", {})
            for key in ("path", "file"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    paths.append(value)
            for key in ("file_anchors",):
                for value in body.get(key, []):
                    if isinstance(value, str) and value:
                        paths.append(value)
            for bucket in ("primary_context", "example_patterns", "optional_context", "supporting_context", "tests_to_consider"):
                for nested in body.get(bucket, []):
                    if isinstance(nested, dict):
                        value = nested.get("path")
                        if isinstance(value, str) and value:
                            paths.append(value)
    for signal in content.get("key_signals", []):
        value = signal.get("value")
        if isinstance(value, str):
            paths.append(value)
    for step in content.get("suggested_next_steps", []):
        value = step.get("value")
        if isinstance(value, str):
            paths.append(value)
    return paths


def _thinness_flags(case: TaskEvalCase, result: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    content = result["content"]
    if not content.get("key_signals"):
        flags.append("no_key_signals")
    if not content.get("suggested_next_steps"):
        flags.append("no_suggested_next_steps")
    tool_map = {
        "agentic_devdocs": "docs_results",
        "agentic_indexer": "code_results",
        "agentic_sitemap": "site_results",
    }
    for tool in case.expected_tools:
        group_name = tool_map[tool]
        if not content.get(group_name):
            flags.append(f"missing_{group_name}")
        expected_step_source = tool
        if not any(step.get("source_tool") == expected_step_source for step in content.get("suggested_next_steps", [])):
            flags.append(f"missing_{tool}_next_step")
    return flags


def _noise_flags(result: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    seen: set[tuple[str, str]] = set()
    for step in result["content"].get("suggested_next_steps", []):
        value = str(step.get("value", ""))
        key = (str(step.get("kind", "")), value)
        if key in seen and "duplicate_next_steps" not in flags:
            flags.append("duplicate_next_steps")
        seen.add(key)
        if value.startswith("//") or "://" in value:
            flags.append("external_like_next_step")
    return flags
