# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Runtime health and drift checks for the local orchestrator environment."""

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


STATUS_ORDER = {"OK": 0, "WARNING": 1, "FAIL": 2}
DEFAULT_THRESHOLDS = {
    "devdocs_db_hours": 24 * 30,
    "indexer_db_hours": 24 * 14,
    "sitemap_run_hours": 24 * 7,
}
BASELINE_ROUTING_SUMMARY = {"CORRECT": 30, "ACCEPTABLE": 2, "OVERCALLED": 0, "UNDERCALLED": 0, "WRONG": 0}
BASELINE_TASK_SUMMARY = {"COMPLETE": 5, "PARTIAL": 0, "INSUFFICIENT": 0}


@dataclass(frozen=True)
class HealthCheckResult:
    """One concrete health check outcome."""

    name: str
    status: str
    summary: str
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

    overall = _overall_status(checks)
    return {
        "overall_status": overall,
        "generated_at": current.isoformat(),
        "deep": deep,
        "thresholds": active_thresholds,
        "checks": [
            {
                "name": item.name,
                "status": item.status,
                "summary": item.summary,
                "details": item.details,
            }
            for item in checks
        ],
        "notes": [
            "Health checks are conservative and intended to catch obvious local drift.",
            "A WARNING indicates possible staleness or trust erosion; a FAIL indicates the local runtime is not trustworthy enough to proceed normally.",
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
    ]
    for check in report["checks"]:
        lines.append(f"[{check['status']}] {check['name']}: {check['summary']}")
    if report["notes"]:
        lines.extend(["", "Notes:"])
        for note in report["notes"]:
            lines.append(f"- {note}")
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
                    status="FAIL",
                    summary=str(exc),
                    details={"program": tool.command[0] if tool.command else None, "workdir": tool.workdir},
                )
            )
            continue
        checks.append(
            HealthCheckResult(
                name=f"tool.{tool_name}",
                status="OK",
                summary="tool command and workdir resolved successfully",
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
                    status="FAIL",
                    summary=str(exc),
                    details={"program": tool.command[0] if tool.command else None, "workdir": tool.workdir},
                )
            )
        else:
            checks.append(
                HealthCheckResult(
                    name="tool.agentic_debug",
                    status="OK",
                    summary="tool command and workdir resolved successfully",
                    details={"program": tool.resolved_program(), "workdir": tool.workdir},
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
        return HealthCheckResult(name=name, status="FAIL", summary="resource path is not configured", details={"path": None})
    path = Path(raw_path).expanduser()
    if not path.exists():
        return HealthCheckResult(name=name, status="FAIL", summary="resource path does not exist", details={"path": str(path)})
    if expected_kind == "file" and not path.is_file():
        return HealthCheckResult(name=name, status="FAIL", summary="resource path is not a file", details={"path": str(path)})
    if expected_kind == "dir" and not path.is_dir():
        return HealthCheckResult(name=name, status="FAIL", summary="resource path is not a directory", details={"path": str(path)})

    mtime = _resource_mtime(path)
    age_hours = (now.timestamp() - mtime.timestamp()) / 3600
    status = "OK"
    summary = "resource exists and is recent enough"
    if age_hours > max_age_hours:
        status = "WARNING"
        summary = "resource exists but appears stale"
    return HealthCheckResult(
        name=name,
        status=status,
        summary=summary,
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
        specs.append(
            (
                "contract.agentic_debug",
                lambda: adapters.debug.health(),
            )
        )
    for name, call in specs:
        try:
            payload = call()
        except (ConfigurationError, ToolExecutionError) as exc:
            checks.append(HealthCheckResult(name=name, status="FAIL", summary=str(exc), details={}))
            continue
        checks.append(
            HealthCheckResult(
                name=name,
                status="OK",
                summary="runtime contract sanity call validated",
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
        return HealthCheckResult(name=name, status="OK", summary="deep baseline matches expected summary", details={"actual": actual, "expected": expected})
    return HealthCheckResult(
        name=name,
        status="WARNING",
        summary="deep baseline differs from the expected summary",
        details={"actual": actual, "expected": expected},
    )


def _overall_status(checks: list[HealthCheckResult]) -> str:
    highest = max((STATUS_ORDER[item.status] for item in checks), default=0)
    for status, value in STATUS_ORDER.items():
        if value == highest:
            return status
    return "OK"
