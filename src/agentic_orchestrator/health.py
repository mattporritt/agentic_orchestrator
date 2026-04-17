# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Runtime health, readiness, and drift checks for the local orchestrator environment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_orchestrator.adapters import AdapterSet, Runner
from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.errors import ConfigurationError, ToolExecutionError
from agentic_orchestrator.orchestrator import OrchestratorService
from agentic_orchestrator.routing import ToolRequest
from agentic_orchestrator.routing_eval import evaluate_auto_routing
from agentic_orchestrator.task_eval import evaluate_task_outputs


DEFAULT_THRESHOLDS = {
    "devdocs_db_hours": 24 * 30,
    "indexer_db_hours": 24 * 14,
    "sitemap_run_hours": 24 * 7,
}
BASELINE_ROUTING_SUMMARY = {"CORRECT": 30, "ACCEPTABLE": 2, "OVERCALLED": 0, "UNDERCALLED": 0, "WRONG": 0}
BASELINE_TASK_SUMMARY = {"COMPLETE": 5, "PARTIAL": 0, "INSUFFICIENT": 0}
CAPABILITY_REQUIREMENTS = {
    "docs_lookup": ["tool.agentic_devdocs", "resource.devdocs_db", "contract.agentic_devdocs"],
    "code_context": ["tool.agentic_indexer", "resource.indexer_db", "contract.agentic_indexer"],
    "site_navigation": ["tool.agentic_sitemap", "resource.sitemap_run", "contract.agentic_sitemap"],
    "debug_investigation": ["tool.agentic_debug", "contract.agentic_debug"],
}
HEALTHY_QUERY = "add admin settings to a plugin"


@dataclass(frozen=True)
class HealthCheckResult:
    """One concrete health/readiness check outcome."""

    name: str
    category: str
    subject: str
    status: str
    impact: str
    summary: str
    capabilities: tuple[str, ...]
    details: dict[str, Any]


def collect_health_report(
    config: OrchestratorConfig,
    *,
    runner: Runner | None = None,
    now: datetime | None = None,
    deep: bool = False,
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Inspect local tool wiring, resources, recency, and contract sanity."""

    current = now or datetime.now(UTC)
    active_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    checks: list[HealthCheckResult] = []

    checks.extend(_tool_checks(config))
    checks.extend(_resource_checks(config, now=current, thresholds=active_thresholds))
    checks.extend(_contract_checks(config, runner=runner))
    if deep:
        checks.extend(_deep_baseline_checks(config, runner=runner))

    warnings = [_issue_view(item) for item in checks if item.status == "WARNING"]
    blocking_issues = [_issue_view(item) for item in checks if item.impact == "blocking" and item.status == "FAIL"]
    non_blocking_issues = [
        _issue_view(item)
        for item in checks
        if item.impact == "non_blocking" and item.status in {"WARNING", "FAIL"}
    ]
    capability_status = _capability_status_map(checks)
    usable_for = {name: status in {"OK", "WARNING"} for name, status in capability_status.items()}
    trusted_capabilities = [name for name, status in capability_status.items() if status == "OK"]

    return {
        "overall_status": _overall_health_status(blocking_issues=blocking_issues, warnings=warnings, non_blocking_issues=non_blocking_issues),
        "generated_at": current.isoformat(),
        "deep": deep,
        "thresholds": active_thresholds,
        "checks": [_serialize_check(item) for item in checks],
        "warnings": warnings,
        "blocking_issues": blocking_issues,
        "non_blocking_issues": non_blocking_issues,
        "per_tool_status": _per_subject_status(checks, category="tool"),
        "per_resource_status": _per_subject_status(checks, category="resource"),
        "capability_status": capability_status,
        "usable_for": usable_for,
        "trusted_capabilities": trusted_capabilities,
        "notes": [
            "Health checks are conservative and intended to catch obvious local drift.",
            "FAIL plus impact=blocking means the orchestrator is not trustworthy enough for normal use in that capability.",
            "WARNING means degraded-but-usable, while FAIL plus impact=non_blocking means an optional capability is unavailable.",
        ],
    }


def render_health_text(report: dict[str, Any]) -> str:
    """Render a concise human-readable health report."""

    lines = [
        "Runtime Health",
        "",
        f"Overall: {report['overall_status']}",
        f"Generated: {report['generated_at']}",
        f"Deep checks: {'enabled' if report['deep'] else 'disabled'}",
        "",
        "Usable For:",
    ]
    for capability, usable in report["usable_for"].items():
        status = report["capability_status"][capability]
        lines.append(f"- {capability}: {'yes' if usable else 'no'} ({status})")
    if report["trusted_capabilities"]:
        lines.extend(["", f"Trusted capabilities: {', '.join(report['trusted_capabilities'])}"])
    if report["blocking_issues"]:
        lines.extend(["", "Blocking issues:"])
        for issue in report["blocking_issues"]:
            lines.append(f"- {issue['name']}: {issue['summary']}")
    if report["non_blocking_issues"]:
        lines.extend(["", "Non-blocking issues:"])
        for issue in report["non_blocking_issues"]:
            lines.append(f"- {issue['name']}: {issue['summary']}")
    lines.extend(["", "Checks:"])
    for check in report["checks"]:
        lines.append(f"[{check['status']}] {check['name']}: {check['summary']}")
    if report["notes"]:
        lines.extend(["", "Notes:"])
        for note in report["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def collect_verify_report(
    config: OrchestratorConfig,
    *,
    runner: Runner | None = None,
    now: datetime | None = None,
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Run a conservative readiness check for real orchestrated use."""

    health_report = collect_health_report(config, runner=runner, now=now, deep=False, thresholds=thresholds)
    query_sanity = _query_sanity_check(config, runner=runner, health_report=health_report)

    blocking_issues = list(health_report["blocking_issues"])
    non_blocking_issues = list(health_report["non_blocking_issues"])
    if query_sanity["impact"] == "blocking" and query_sanity["status"] == "FAIL":
        blocking_issues.append(query_sanity)
    elif query_sanity["status"] in {"WARNING", "FAIL"}:
        non_blocking_issues.append(query_sanity)

    if blocking_issues:
        overall_status = "NOT_READY"
    elif non_blocking_issues or health_report["overall_status"] == "WARNING":
        overall_status = "DEGRADED"
    else:
        overall_status = "READY"

    return {
        "overall_status": overall_status,
        "generated_at": health_report["generated_at"],
        "health_overall_status": health_report["overall_status"],
        "query_sanity": query_sanity,
        "blocking_issues": blocking_issues,
        "non_blocking_issues": non_blocking_issues,
        "trusted_capabilities": health_report["trusted_capabilities"],
        "usable_for": health_report["usable_for"],
        "capability_status": health_report["capability_status"],
        "notes": [
            "Verify wraps config/resource/contract health with one lightweight orchestrator query sanity check.",
            "READY means healthy enough for normal use right now; DEGRADED means usable with caution; NOT_READY means blocking issues remain.",
        ],
    }


def render_verify_text(report: dict[str, Any]) -> str:
    """Render a concise human-readable readiness report."""

    lines = [
        "Runtime Readiness",
        "",
        f"Overall: {report['overall_status']}",
        f"Generated: {report['generated_at']}",
        f"Health: {report['health_overall_status']}",
        "",
        "Usable For:",
    ]
    for capability, usable in report["usable_for"].items():
        status = report["capability_status"][capability]
        lines.append(f"- {capability}: {'yes' if usable else 'no'} ({status})")
    lines.extend(
        [
            "",
            f"Query sanity: {report['query_sanity']['status']} -> {report['query_sanity']['summary']}",
        ]
    )
    if report["blocking_issues"]:
        lines.extend(["", "Blocking issues:"])
        for issue in report["blocking_issues"]:
            lines.append(f"- {issue['name']}: {issue['summary']}")
    if report["non_blocking_issues"]:
        lines.extend(["", "Non-blocking issues:"])
        for issue in report["non_blocking_issues"]:
            lines.append(f"- {issue['name']}: {issue['summary']}")
    return "\n".join(lines) + "\n"


def _tool_checks(config: OrchestratorConfig) -> list[HealthCheckResult]:
    checks: list[HealthCheckResult] = []
    for tool_name in ("agentic_devdocs", "agentic_indexer", "agentic_sitemap"):
        tool = config.tool_config(tool_name)
        try:
            tool.validate()
        except ConfigurationError as exc:
            checks.append(
                HealthCheckResult(
                    name=f"tool.{tool_name}",
                    category="tool",
                    subject=tool_name,
                    status="FAIL",
                    impact="blocking",
                    summary=str(exc),
                    capabilities=_tool_capabilities(tool_name),
                    details={"program": tool.command[0] if tool.command else None, "workdir": tool.workdir},
                )
            )
            continue
        checks.append(
            HealthCheckResult(
                name=f"tool.{tool_name}",
                category="tool",
                subject=tool_name,
                status="OK",
                impact="info",
                summary="tool command and workdir resolved successfully",
                capabilities=_tool_capabilities(tool_name),
                details={"program": tool.resolved_program(), "workdir": tool.workdir},
            )
        )

    if config.debug.command:
        tool = config.debug
        try:
            tool.validate()
        except ConfigurationError as exc:
            checks.append(
                HealthCheckResult(
                    name="tool.agentic_debug",
                    category="tool",
                    subject="agentic_debug",
                    status="FAIL",
                    impact="non_blocking",
                    summary=str(exc),
                    capabilities=("debug_investigation",),
                    details={"program": tool.command[0] if tool.command else None, "workdir": tool.workdir},
                )
            )
        else:
            checks.append(
                HealthCheckResult(
                    name="tool.agentic_debug",
                    category="tool",
                    subject="agentic_debug",
                    status="OK",
                    impact="info",
                    summary="tool command and workdir resolved successfully",
                    capabilities=("debug_investigation",),
                    details={"program": tool.resolved_program(), "workdir": tool.workdir},
                )
            )
    else:
        checks.append(
            HealthCheckResult(
                name="tool.agentic_debug",
                category="tool",
                subject="agentic_debug",
                status="FAIL",
                impact="non_blocking",
                summary="debug tool is not configured",
                capabilities=("debug_investigation",),
                details={"program": None, "workdir": None},
            )
        )
    return checks


def _resource_checks(config: OrchestratorConfig, *, now: datetime, thresholds: dict[str, int]) -> list[HealthCheckResult]:
    return [
        _resource_check("resource.devdocs_db", config.devdocs_db_path, "file", now=now, max_age_hours=thresholds["devdocs_db_hours"]),
        _resource_check("resource.indexer_db", config.indexer_db_path, "file", now=now, max_age_hours=thresholds["indexer_db_hours"]),
        _resource_check("resource.sitemap_run", config.sitemap_run_dir, "dir", now=now, max_age_hours=thresholds["sitemap_run_hours"]),
    ]


def _resource_check(
    name: str,
    raw_path: str | None,
    expected_kind: str,
    *,
    now: datetime,
    max_age_hours: int,
) -> HealthCheckResult:
    if not raw_path:
        return HealthCheckResult(
            name=name,
            category="resource",
            subject=name.split(".", 1)[1],
            status="FAIL",
            impact="blocking",
            summary="resource path is not configured",
            capabilities=_resource_capabilities(name),
            details={"path": None},
        )
    path = Path(raw_path).expanduser()
    if not path.exists():
        return HealthCheckResult(
            name=name,
            category="resource",
            subject=name.split(".", 1)[1],
            status="FAIL",
            impact="blocking",
            summary="resource path does not exist",
            capabilities=_resource_capabilities(name),
            details={"path": str(path)},
        )
    if expected_kind == "file" and not path.is_file():
        return HealthCheckResult(
            name=name,
            category="resource",
            subject=name.split(".", 1)[1],
            status="FAIL",
            impact="blocking",
            summary="resource path is not a file",
            capabilities=_resource_capabilities(name),
            details={"path": str(path)},
        )
    if expected_kind == "dir" and not path.is_dir():
        return HealthCheckResult(
            name=name,
            category="resource",
            subject=name.split(".", 1)[1],
            status="FAIL",
            impact="blocking",
            summary="resource path is not a directory",
            capabilities=_resource_capabilities(name),
            details={"path": str(path)},
        )

    mtime = _resource_mtime(path)
    age_hours = (now.timestamp() - mtime.timestamp()) / 3600
    status = "OK"
    impact = "info"
    summary = "resource exists and is recent enough"
    if age_hours > max_age_hours:
        status = "WARNING"
        impact = "non_blocking"
        summary = "resource exists but appears stale"
    return HealthCheckResult(
        name=name,
        category="resource",
        subject=name.split(".", 1)[1],
        status=status,
        impact=impact,
        summary=summary,
        capabilities=_resource_capabilities(name),
        details={
            "path": str(path),
            "mtime": mtime.isoformat(),
            "age_hours": round(age_hours, 2),
            "max_age_hours": max_age_hours,
        },
    )


def _resource_mtime(path: Path) -> datetime:
    if path.is_dir():
        mtimes = [item.stat().st_mtime for item in path.rglob("*") if item.exists()]
        candidate = max(mtimes) if mtimes else path.stat().st_mtime
        return datetime.fromtimestamp(candidate, tz=UTC)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _contract_checks(config: OrchestratorConfig, *, runner: Runner | None = None) -> list[HealthCheckResult]:
    adapters = AdapterSet.from_config(config, runner=runner)
    checks: list[HealthCheckResult] = []
    specs = [
        (
            "contract.agentic_devdocs",
            lambda: adapters.devdocs.query(db_path=str(config.devdocs_db_path or ""), query="admin settings", top_k=1),
        ),
        (
            "contract.agentic_indexer",
            lambda: adapters.indexer.query(
                db_path=str(config.indexer_db_path or ""),
                request=ToolRequest(tool_name="agentic_indexer", reason="health sanity", mode="build-context-bundle", query="define a web service"),
                limit=1,
            ),
        ),
        (
            "contract.agentic_sitemap",
            lambda: adapters.sitemap.query(
                run_dir=str(config.sitemap_run_dir or ""),
                request=ToolRequest(tool_name="agentic_sitemap", reason="health sanity", mode="runtime-query", lookup_mode="page_type", query="dashboard"),
                top_k=1,
            ),
        ),
    ]
    if config.debug.command:
        specs.append(("contract.agentic_debug", lambda: adapters.debug.health()))
    for name, call in specs:
        try:
            payload = call()
        except (ConfigurationError, ToolExecutionError) as exc:
            checks.append(
                HealthCheckResult(
                    name=name,
                    category="contract",
                    subject=name.split(".", 1)[1],
                    status="FAIL",
                    impact="non_blocking" if name == "contract.agentic_debug" else "blocking",
                    summary=str(exc),
                    capabilities=_contract_capabilities(name),
                    details={},
                )
            )
            continue
        checks.append(
            HealthCheckResult(
                name=name,
                category="contract",
                subject=name.split(".", 1)[1],
                status="OK",
                impact="info",
                summary="runtime contract sanity call validated",
                capabilities=_contract_capabilities(name),
                details={
                    "tool": payload["tool"],
                    "version": payload["version"],
                    "result_count": len(payload["results"]),
                },
            )
        )
    return checks


def _deep_baseline_checks(config: OrchestratorConfig, *, runner: Runner | None = None) -> list[HealthCheckResult]:
    service = OrchestratorService.from_config(config, runner=runner)
    routing_summary = evaluate_auto_routing(service)["summary"]
    task_summary = evaluate_task_outputs(service)["summary"]
    return [
        _baseline_check("baseline.routing_eval", routing_summary, BASELINE_ROUTING_SUMMARY),
        _baseline_check("baseline.task_eval", task_summary, BASELINE_TASK_SUMMARY),
    ]


def _baseline_check(name: str, actual: dict[str, int], expected: dict[str, int]) -> HealthCheckResult:
    if actual == expected:
        return HealthCheckResult(
            name=name,
            category="baseline",
            subject=name.split(".", 1)[1],
            status="OK",
            impact="info",
            summary="deep baseline matches expected summary",
            capabilities=(),
            details={"actual": actual, "expected": expected},
        )
    return HealthCheckResult(
        name=name,
        category="baseline",
        subject=name.split(".", 1)[1],
        status="WARNING",
        impact="non_blocking",
        summary="deep baseline differs from the expected summary",
        capabilities=(),
        details={"actual": actual, "expected": expected},
    )


def _query_sanity_check(
    config: OrchestratorConfig,
    *,
    runner: Runner | None,
    health_report: dict[str, Any],
) -> dict[str, Any]:
    if not health_report["usable_for"]["docs_lookup"] or not health_report["usable_for"]["code_context"]:
        return {
            "name": "query_sanity",
            "category": "query_sanity",
            "subject": "orchestrator",
            "status": "FAIL",
            "impact": "blocking",
            "summary": "lightweight query sanity check could not run because docs/code capabilities are unavailable",
            "capabilities": ["docs_lookup", "code_context", "pattern_discovery"],
            "details": {"query": HEALTHY_QUERY, "route_mode": "task"},
        }

    service = OrchestratorService.from_config(config, runner=runner)
    try:
        payload = service.query(query=HEALTHY_QUERY, route_mode="task")
    except (ConfigurationError, ToolExecutionError) as exc:
        return {
            "name": "query_sanity",
            "category": "query_sanity",
            "subject": "orchestrator",
            "status": "FAIL",
            "impact": "blocking",
            "summary": str(exc),
            "capabilities": ["docs_lookup", "code_context", "pattern_discovery"],
            "details": {"query": HEALTHY_QUERY, "route_mode": "task"},
        }

    result = payload["results"][0]
    content = result["content"]
    diagnostics = result["diagnostics"]
    if content.get("result_thin"):
        return {
            "name": "query_sanity",
            "category": "query_sanity",
            "subject": "orchestrator",
            "status": "WARNING",
            "impact": "non_blocking",
            "summary": "lightweight query succeeded but returned thin refinement signals",
            "capabilities": ["docs_lookup", "code_context", "pattern_discovery"],
            "details": {
                "query": HEALTHY_QUERY,
                "route_mode": "task",
                "selected_tools": diagnostics.get("selected_tools", []),
                "missing_key_signals": content.get("missing_key_signals", []),
                "refine_query_hints": content.get("refine_query_hints", []),
            },
        }
    return {
        "name": "query_sanity",
        "category": "query_sanity",
        "subject": "orchestrator",
        "status": "OK",
        "impact": "info",
        "summary": "lightweight query sanity check succeeded",
        "capabilities": ["docs_lookup", "code_context", "pattern_discovery"],
        "details": {
            "query": HEALTHY_QUERY,
            "route_mode": "task",
            "selected_tools": diagnostics.get("selected_tools", []),
        },
    }


def _serialize_check(item: HealthCheckResult) -> dict[str, Any]:
    return {
        "name": item.name,
        "category": item.category,
        "subject": item.subject,
        "status": item.status,
        "impact": item.impact,
        "summary": item.summary,
        "capabilities": list(item.capabilities),
        "details": item.details,
    }


def _issue_view(item: HealthCheckResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, HealthCheckResult):
        return _serialize_check(item)
    return {
        "name": item["name"],
        "category": item.get("category"),
        "subject": item.get("subject"),
        "status": item["status"],
        "impact": item["impact"],
        "summary": item["summary"],
        "capabilities": list(item.get("capabilities", [])),
        "details": item.get("details", {}),
    }


def _per_subject_status(checks: list[HealthCheckResult], *, category: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[HealthCheckResult]] = {}
    for item in checks:
        if item.category != category:
            continue
        grouped.setdefault(item.subject, []).append(item)
    report: dict[str, dict[str, Any]] = {}
    for subject, items in grouped.items():
        report[subject] = {
            "status": _aggregate_status(item.status for item in items),
            "blocking": any(item.impact == "blocking" and item.status == "FAIL" for item in items),
            "issues": [_issue_view(item) for item in items if item.status in {"WARNING", "FAIL"}],
        }
    return report


def _capability_status_map(checks: list[HealthCheckResult]) -> dict[str, str]:
    name_to_status = {item.name: item.status for item in checks}
    status_map = {
        capability: _aggregate_status(name_to_status.get(name, "FAIL") for name in required_checks)
        for capability, required_checks in CAPABILITY_REQUIREMENTS.items()
    }
    docs_status = status_map["docs_lookup"]
    code_status = status_map["code_context"]
    if docs_status == "FAIL" and code_status == "FAIL":
        status_map["pattern_discovery"] = "FAIL"
    elif docs_status == "OK" and code_status == "OK":
        status_map["pattern_discovery"] = "OK"
    else:
        status_map["pattern_discovery"] = "WARNING"
    return status_map


def _aggregate_status(statuses: Any) -> str:
    values = list(statuses)
    if "FAIL" in values:
        return "FAIL"
    if "WARNING" in values:
        return "WARNING"
    return "OK"


def _overall_health_status(*, blocking_issues: list[dict[str, Any]], warnings: list[dict[str, Any]], non_blocking_issues: list[dict[str, Any]]) -> str:
    if blocking_issues:
        return "FAIL"
    if warnings or non_blocking_issues:
        return "WARNING"
    return "OK"


def _tool_capabilities(tool_name: str) -> tuple[str, ...]:
    mapping = {
        "agentic_devdocs": ("docs_lookup", "pattern_discovery"),
        "agentic_indexer": ("code_context", "pattern_discovery"),
        "agentic_sitemap": ("site_navigation",),
        "agentic_debug": ("debug_investigation",),
    }
    return mapping.get(tool_name, ())


def _resource_capabilities(name: str) -> tuple[str, ...]:
    mapping = {
        "resource.devdocs_db": ("docs_lookup", "pattern_discovery"),
        "resource.indexer_db": ("code_context", "pattern_discovery"),
        "resource.sitemap_run": ("site_navigation",),
    }
    return mapping.get(name, ())


def _contract_capabilities(name: str) -> tuple[str, ...]:
    mapping = {
        "contract.agentic_devdocs": ("docs_lookup", "pattern_discovery"),
        "contract.agentic_indexer": ("code_context", "pattern_discovery"),
        "contract.agentic_sitemap": ("site_navigation",),
        "contract.agentic_debug": ("debug_investigation",),
    }
    return mapping.get(name, ())
