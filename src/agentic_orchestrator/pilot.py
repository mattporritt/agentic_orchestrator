# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Lightweight file-based harness for supervised pilot trials.

The pilot runner records real orchestrator runs plus a compact human outcome so
trial usage can be inspected later without adding a database or service.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_orchestrator.config import OrchestratorConfig, resolve_repo_root
from agentic_orchestrator.orchestrator import OrchestratorService


OUTCOME_VALUES = ("useful", "partially_useful", "misleading", "not_reviewed")


def default_pilot_root() -> Path:
    """Return the default on-disk location for pilot trial artifacts."""

    return resolve_repo_root() / "_smoke_test" / "pilot_runs"


def create_pilot_trial(
    service: OrchestratorService,
    config: OrchestratorConfig,
    *,
    query: str,
    route_mode: str,
    manual_tools: list[str] | None = None,
    context: dict[str, Any] | None = None,
    task_label: str | None = None,
    notes: str | None = None,
    pilot_root: str | None = None,
    outcome: str = "not_reviewed",
    review_notes: str | None = None,
    files_touched: list[str] | None = None,
    did_it_help_find_right_files: bool | None = None,
    did_it_help_find_right_docs: bool | None = None,
) -> Path:
    """Run the orchestrator and persist one timestamped pilot trial artifact."""

    created_at = datetime.now(UTC)
    trial_id = _build_trial_id(created_at, task_label or query)
    root = Path(pilot_root).expanduser() if pilot_root else default_pilot_root()
    trial_dir = root / trial_id
    trial_dir.mkdir(parents=True, exist_ok=False)

    payload = service.query(query=query, context=context, route_mode=route_mode, manual_tools=manual_tools)
    selected_tools = payload["results"][0]["diagnostics"]["selected_tools"]
    artifact = {
        "trial_id": trial_id,
        "created_at": created_at.isoformat(),
        "query": query,
        "route_mode": route_mode,
        "manual_tools": list(manual_tools or []),
        "task_label": task_label,
        "notes": notes,
        "context": context or {},
        "config_path": config.config_path,
        "selected_tools": selected_tools,
        "outcome": _outcome_record(
            outcome=outcome,
            notes=review_notes,
            files_touched=files_touched,
            did_it_help_find_right_files=did_it_help_find_right_files,
            did_it_help_find_right_docs=did_it_help_find_right_docs,
        ),
        "orchestrator_output": payload,
    }
    _write_trial_artifact(trial_dir, artifact)
    return trial_dir


def update_pilot_trial(
    trial_ref: str,
    *,
    pilot_root: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
    files_touched: list[str] | None = None,
    did_it_help_find_right_files: bool | None = None,
    did_it_help_find_right_docs: bool | None = None,
) -> Path:
    """Update the human review outcome for an existing pilot trial."""

    trial_dir = resolve_pilot_trial(trial_ref, pilot_root=pilot_root)
    artifact_path = trial_dir / "trial.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    current = artifact.get("outcome", {})
    artifact["outcome"] = _outcome_record(
        outcome=outcome or current.get("outcome", "not_reviewed"),
        notes=notes if notes is not None else current.get("notes"),
        files_touched=files_touched if files_touched is not None else current.get("files_touched", []),
        did_it_help_find_right_files=(
            did_it_help_find_right_files
            if did_it_help_find_right_files is not None
            else current.get("did_it_help_find_right_files")
        ),
        did_it_help_find_right_docs=(
            did_it_help_find_right_docs if did_it_help_find_right_docs is not None else current.get("did_it_help_find_right_docs")
        ),
    )
    _write_trial_artifact(trial_dir, artifact)
    return trial_dir


def collect_pilot_report(*, pilot_root: str | None = None) -> dict[str, Any]:
    """Summarize all recorded pilot trials under the configured root."""

    root = Path(pilot_root).expanduser() if pilot_root else default_pilot_root()
    trials = list(_iter_trial_artifacts(root))
    outcome_counts = Counter()
    route_mode_counts = Counter()
    label_counts = Counter()
    tool_counts = Counter()
    records: list[dict[str, Any]] = []

    for artifact in trials:
        outcome = artifact.get("outcome", {}).get("outcome", "not_reviewed")
        route_mode = artifact.get("route_mode", "task")
        label = artifact.get("task_label") or "(unlabeled)"
        selected_tools = list(artifact.get("selected_tools", []))
        outcome_counts[outcome] += 1
        route_mode_counts[route_mode] += 1
        label_counts[label] += 1
        for tool in selected_tools:
            tool_counts[tool] += 1
        records.append(
            {
                "trial_id": artifact["trial_id"],
                "created_at": artifact["created_at"],
                "query": artifact["query"],
                "route_mode": route_mode,
                "task_label": artifact.get("task_label"),
                "outcome": outcome,
                "selected_tools": selected_tools,
            }
        )

    return {
        "pilot_root": str(root),
        "total_runs": len(trials),
        "by_outcome": dict(sorted(outcome_counts.items())),
        "by_route_mode": dict(sorted(route_mode_counts.items())),
        "by_task_label": dict(sorted(label_counts.items())),
        "by_tools_used": dict(sorted(tool_counts.items())),
        "trials": sorted(records, key=lambda item: item["created_at"]),
    }


def render_pilot_report_text(report: dict[str, Any]) -> str:
    """Render a compact human-readable pilot trial summary."""

    lines = [
        "Pilot Report",
        "",
        f"Pilot root: {report['pilot_root']}",
        f"Total runs: {report['total_runs']}",
        "",
        "By outcome:",
    ]
    if report["by_outcome"]:
        for name, count in report["by_outcome"].items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "By route mode:"])
    if report["by_route_mode"]:
        for name, count in report["by_route_mode"].items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "By task label:"])
    if report["by_task_label"]:
        for name, count in report["by_task_label"].items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "By tools used:"])
    if report["by_tools_used"]:
        for name, count in report["by_tools_used"].items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none")
    if report["trials"]:
        lines.extend(["", "Trials:"])
        for item in report["trials"]:
            lines.append(
                f"- {item['trial_id']}: {item['outcome']} | mode={item['route_mode']} | tools={', '.join(item['selected_tools']) or '(none)'}"
            )
    return "\n".join(lines) + "\n"


def resolve_pilot_trial(trial_ref: str, *, pilot_root: str | None = None) -> Path:
    """Resolve a pilot trial by absolute path, relative path, or trial id."""

    candidate = Path(trial_ref).expanduser()
    if candidate.exists():
        return candidate if candidate.is_dir() else candidate.parent
    root = Path(pilot_root).expanduser() if pilot_root else default_pilot_root()
    direct = root / trial_ref
    if direct.exists():
        return direct
    matches = [path for path in root.glob("*/trial.json") if path.parent.name == trial_ref]
    if matches:
        return matches[0].parent
    raise FileNotFoundError(f"Pilot trial not found: {trial_ref}")


def _iter_trial_artifacts(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/trial.json")):
        artifacts.append(json.loads(path.read_text(encoding="utf-8")))
    return artifacts


def _outcome_record(
    *,
    outcome: str,
    notes: str | None,
    files_touched: list[str] | None,
    did_it_help_find_right_files: bool | None,
    did_it_help_find_right_docs: bool | None,
) -> dict[str, Any]:
    if outcome not in OUTCOME_VALUES:
        raise ValueError(f"Unsupported pilot outcome '{outcome}'.")
    return {
        "outcome": outcome,
        "notes": notes,
        "files_touched": list(files_touched or []),
        "did_it_help_find_right_files": did_it_help_find_right_files,
        "did_it_help_find_right_docs": did_it_help_find_right_docs,
    }


def _write_trial_artifact(trial_dir: Path, artifact: dict[str, Any]) -> None:
    (trial_dir / "trial.json").write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    (trial_dir / "summary.md").write_text(_render_trial_summary(artifact), encoding="utf-8")


def _build_trial_id(created_at: datetime, source: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in source).strip("-")
    slug = "-".join(part for part in slug.split("-") if part)[:48] or "trial"
    return f"{created_at.strftime('%Y%m%d_%H%M%S')}_{slug}"


def _render_trial_summary(artifact: dict[str, Any]) -> str:
    result = artifact["orchestrator_output"]["results"][0]
    outcome = artifact["outcome"]
    lines = [
        f"# Pilot Trial {artifact['trial_id']}",
        "",
        f"- Query: `{artifact['query']}`",
        f"- Route mode: `{artifact['route_mode']}`",
        f"- Task label: `{artifact['task_label'] or '(none)'}`",
        f"- Selected tools: `{', '.join(artifact['selected_tools']) or '(none)'}`",
        f"- Outcome: `{outcome['outcome']}`",
    ]
    if artifact.get("notes"):
        lines.append(f"- Run notes: {artifact['notes']}")
    if outcome.get("notes"):
        lines.append(f"- Review notes: {outcome['notes']}")
    lines.extend(
        [
            "",
            "## Summary",
            "",
            result["content"]["summary"],
            "",
            "## Suggested Next Steps",
            "",
        ]
    )
    for step in result["content"]["suggested_next_steps"][:8]:
        lines.append(f"- [{step['source_tool']}] {step['kind']}: {step['value']}")
    return "\n".join(lines) + "\n"
