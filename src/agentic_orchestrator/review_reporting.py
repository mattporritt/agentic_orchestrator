"""Formatting and serialization helpers for review artifact bundles.

This module keeps bundle reporting concerns separate from the subprocess and
artifact-writing flow in ``review_bundle.py`` so the bundle generator can stay
focused on orchestration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_orchestrator.config import OrchestratorConfig


def serializable_routing_eval(evaluation: dict[str, object]) -> dict[str, object]:
    """Return a JSON-stable subset of the routing evaluation payload."""

    return {
        "summary": evaluation["summary"],
        "by_query_style": evaluation["by_query_style"],
        "cases": [
            {
                "case_id": case["case_id"],
                "query": case["query"],
                "query_style": case["query_style"],
                "preferred_tools": case["preferred_tools"],
                "acceptable_tool_sets": case["acceptable_tool_sets"],
                "disallowed_tools": case["disallowed_tools"],
                "selected_tools": case["selected_tools"],
                "status": case["status"],
                "reason": case["reason"],
                "notes": case["notes"],
            }
            for case in evaluation["cases"]
        ],
    }


def serializable_task_eval(evaluation: dict[str, object]) -> dict[str, object]:
    """Return a compact, JSON-stable subset of the task evaluation payload."""

    return {
        "summary": evaluation["summary"],
        "cases": [
            {
                "case_id": case["case_id"],
                "query": case["query"],
                "route_mode": case["route_mode"],
                "expected_tools": case["expected_tools"],
                "selected_tools": case["selected_tools"],
                "status": case["status"],
                "reason": case["reason"],
                "key_signals_present": case["key_signals_present"],
                "missing_signals": case["missing_signals"],
                "thinness_flags": case["thinness_flags"],
                "noise_flags": case["noise_flags"],
                "assembly_notes": case["assembly_notes"],
                "notes": case["notes"],
            }
            for case in evaluation["cases"]
        ],
    }


def render_mode_comparison_markdown(comparisons: list[dict[str, object]]) -> str:
    """Render a compact Markdown comparison across task/auto/manual modes."""

    lines = ["# Mode Comparison", ""]
    for item in comparisons:
        lines.append(f"- `{item['case_id']}`")
        lines.append(f"  task: {', '.join(item['task_tools'])}")
        lines.append(f"  auto: {', '.join(item['auto_tools'])}")
        lines.append(f"  manual: {', '.join(item['manual_tools'])}")
    return "\n".join(lines) + "\n"


def sanitized_config_report(config: OrchestratorConfig) -> dict[str, object]:
    """Return a review-safe config snapshot without environment internals."""

    return {
        "config_path": config.config_path,
        "tools": config.tool_path_report(),
        "resources": {
            "devdocs_db_path": config.devdocs_db_path,
            "indexer_db_path": config.indexer_db_path,
            "sitemap_run_dir": config.sitemap_run_dir,
        },
    }


def serializable_health_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-stable subset of the runtime health report."""

    return {
        "overall_status": report["overall_status"],
        "generated_at": report["generated_at"],
        "deep": report["deep"],
        "thresholds": report["thresholds"],
        "checks": [
            {
                "name": check["name"],
                "status": check["status"],
                "summary": check["summary"],
                "details": check["details"],
            }
            for check in report["checks"]
        ],
        "notes": list(report["notes"]),
    }


def build_review_summary(
    *,
    bundle_dir: Path,
    runtime_mode: str,
    config_path: str | None,
    config: OrchestratorConfig,
    task_evaluation: dict[str, Any],
    routing_evaluation: dict[str, Any],
    health_report: dict[str, Any] | None = None,
) -> str:
    """Build the human-readable summary for a review bundle.

    The wording here is intentionally explicit so a first-time contributor or
    AI worker can understand what changed and which baselines still hold.
    """

    task_weak_cases = [case for case in task_evaluation["cases"] if case["status"] != "COMPLETE"]
    summary_lines = [
        "# Task Review Summary",
        "",
        "## Runtime Mode",
        "",
        f"- Review bundle execution mode: `{runtime_mode}`",
        f"- Config path: `{config_path or config.config_path or '(none)'}`",
        "",
        "## Task Evaluation Slice",
        "",
        f"- Task cases evaluated: {len(task_evaluation['cases'])}",
        "- Focus: whether the merged orchestrator output is complete, too thin, or too noisy for representative Moodle development tasks",
        "",
        "## Task Usefulness Semantics",
        "",
        "- `COMPLETE`: merged context included the expected tool contributions and required task signals",
        "- `PARTIAL`: merged context was usable but still thin, noisy, or missing one key task signal",
        "- `INSUFFICIENT`: merged context was missing expected tools or too many required task signals",
        "",
        "## Runtime Health / Drift",
        "",
        "- Added a practical `health` command for local sibling-tool path checks, resource presence checks, recency drift warnings, and contract sanity checks",
        "- Health statuses are explicit: `OK`, `WARNING`, `FAIL`",
        "- `--deep` is available for optional routing/task baseline sanity checks",
        "",
        "## Behavior Verification",
        "",
        "- Verified the runtime contract shape via the existing deterministic test suite",
        f"- Task baseline: complete={task_evaluation['summary']['COMPLETE']}, partial={task_evaluation['summary']['PARTIAL']}, insufficient={task_evaluation['summary']['INSUFFICIENT']}",
        f"- Routing baseline: correct={routing_evaluation['summary']['CORRECT']}, acceptable={routing_evaluation['summary']['ACCEPTABLE']}, overcalled={routing_evaluation['summary']['OVERCALLED']}, undercalled={routing_evaluation['summary']['UNDERCALLED']}, wrong={routing_evaluation['summary']['WRONG']}",
        "",
        "## Representative Task Cases",
        "",
    ]
    for case in task_evaluation["cases"]:
        summary_lines.append(
            f"- `{case['case_id']}`: {case['status']} -> tools={', '.join(case['selected_tools'])}; present={', '.join(case['key_signals_present']) or '(none)'}"
        )
    if health_report is not None:
        summary_lines.extend(["", "## Health Snapshot", ""])
        summary_lines.append(f"- Overall health: {health_report['overall_status']}")
        summary_lines.append(f"- Deep checks in bundle artifact: {'enabled' if health_report['deep'] else 'disabled'}")
        for check in health_report["checks"]:
            summary_lines.append(f"- `{check['name']}`: {check['status']} -> {check['summary']}")
    if task_weak_cases:
        summary_lines.extend(["", "## Thin / Missing / Noisy Cases", ""])
        for case in task_weak_cases:
            line = f"- `{case['case_id']}`: {case['status']}"
            if case["missing_signals"]:
                line += f"; missing={', '.join(case['missing_signals'])}"
            if case["thinness_flags"]:
                line += f"; thinness={', '.join(case['thinness_flags'])}"
            if case["noise_flags"]:
                line += f"; noise={', '.join(case['noise_flags'])}"
            summary_lines.append(line)
    summary_lines.extend(
        [
            "",
            "## Tool Paths Used",
            "",
        ]
    )
    for row in config.tool_path_report():
        summary_lines.append(
            f"- `{row['tool']}` program=`{row['program']}` workdir=`{row['workdir']}` extra_args=`{row['extra_args']}`"
        )
    summary_lines.extend(
        [
            "",
            f"Task review artifact bundle path: {bundle_dir}",
        ]
    )
    return "\n".join(summary_lines) + "\n"
