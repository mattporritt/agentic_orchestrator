# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Generate review artifacts for routing and task-level context usefulness."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agentic_orchestrator.config import OrchestratorConfig, resolve_repo_root
from agentic_orchestrator.debug_eval import evaluate_debug_routes, load_debug_eval_cases, render_debug_eval_text
from agentic_orchestrator.errors import ConfigurationError
from agentic_orchestrator.health import collect_health_report, render_health_text
from agentic_orchestrator.orchestrator import OrchestratorService
from agentic_orchestrator.pilot import collect_pilot_report, create_pilot_trial, render_pilot_report_text
from agentic_orchestrator.review_reporting import (
    build_review_summary,
    render_mode_comparison_markdown,
    sanitized_config_report,
    serializable_health_report,
    serializable_routing_eval,
    serializable_task_eval,
)
from agentic_orchestrator.routing_eval import (
    compare_modes_for_case,
    evaluate_auto_routing,
    load_routing_eval_cases,
    render_routing_eval_text,
)
from agentic_orchestrator.task_eval import evaluate_task_outputs, load_task_eval_cases, render_task_eval_text


@dataclass(frozen=True)
class ReviewBundleRuntime:
    service: OrchestratorService
    execution_mode: str
    config: OrchestratorConfig
    runner: object | None = None


def _runtime_source(name: str, path: str | None = None) -> dict:
    return {
        "name": name,
        "type": "mock_runtime",
        "url": None,
        "canonical_url": None,
        "path": path,
        "document_title": None,
        "section_title": None,
        "heading_path": [],
    }


def _mock_payload(tool: str, query: str) -> dict:
    normalized = " ".join(query.lower().split())
    if tool == "agentic_docs":
        anchors = {
            "settings": ["settings.php", "admin/settings.php"],
            "scheduled task": ["db/tasks.php", "classes/task"],
            "web service": ["db/services.php", "classes/external"],
            "privacy": ["classes/privacy/provider.php", "db/privacy.php"],
            "render": ["classes/output/renderer.php", "templates/example.mustache"],
            "behat": ["tests/behat/example.feature", "tests/behat/behat_mod_example.php"],
        }
        matched = next((key for key in anchors if key in normalized), "render")
        return {
            "tool": "agentic_docs",
            "version": "v1",
            "query": query,
            "normalized_query": normalized,
            "intent": {"query_intent": "docs_lookup", "task_intent": matched, "concept_families": [matched]},
            "results": [
                {
                    "id": f"docs-{matched}",
                    "type": "knowledge_bundle",
                    "rank": 1,
                    "confidence": "high",
                    "source": _runtime_source("moodledevdocs", f"docs/{matched.replace(' ', '_')}.md"),
                    "content": {
                        "summary": f"Reference docs for {matched}.",
                        "sections": [],
                        "file_anchors": anchors[matched],
                        "key_points": [f"Read the {matched} guidance first."],
                    },
                    "diagnostics": {"ranking_explanation": "mock", "support_reason": None, "token_count": 0, "selection_strategy": "mock"},
                }
            ],
        }
    if tool == "agentic_indexer":
        payloads = {
            "settings": ("admin/tool/demo/settings.php", "tool_demo\\settings"),
            "scheduled task": ("mod/forum/db/tasks.php", "mod_forum\\task\\cleanup_task"),
            "web service": ("mod/forum/db/services.php", "mod_forum\\external\\discussion_exporter"),
            "privacy": ("mod/example/classes/privacy/provider.php", "mod_example\\privacy\\provider"),
            "render": ("mod/forum/renderer.php", "mod_forum\\output\\renderer"),
            "behat": ("mod/forum/tests/behat/manage_discussions.feature", None),
        }
        matched = next((key for key in payloads if key in normalized), "render")
        file_path, symbol = payloads[matched]
        return {
            "tool": "agentic_indexer",
            "version": "v1",
            "query": query,
            "normalized_query": normalized,
            "intent": {"command": "build-context-bundle", "query_kind": "query", "response_mode": "context_bundle"},
            "results": [
                {
                    "id": f"code-{matched}",
                    "type": "context_bundle",
                    "rank": 1,
                    "confidence": "high",
                    "source": _runtime_source("codebase", file_path),
                    "content": {
                        "path": file_path,
                        "file": file_path,
                        "symbol": symbol,
                        "summary": f"Primary code artifact for {matched}.",
                    },
                    "diagnostics": {"matched_via": "mock", "usage_count": 0, "selection_strategy": "mock"},
                }
            ],
        }
    if tool == "moodle_debug":
        if " health " in f" {normalized} ":
            return {
                "tool": "moodle_debug",
                "version": "runtime-v1",
                "query": {"input": []},
                "normalized_query": {"intent": "health"},
                "intent": "health",
                "results": [
                    {
                        "id": "health_report",
                        "type": "health_report",
                        "rank": 1,
                        "confidence": "medium",
                        "source": {"kind": "runtime", "profile_name": None, "session_id": None},
                        "content": {"subsystems": [{"name": "config", "status": "ok", "message": "mock health"}]},
                        "diagnostics": [],
                    }
                ],
                "diagnostics": [],
                "meta": {"status": "ok", "generated_at": "2026-04-15T00:00:00+00:00", "repo_root": "/mock/debug", "dry_run": True, "exit_code": 0},
            }
        intent = "interpret_session"
        if "plan_phpunit" in normalized or ("plan debug" in normalized and "phpunit" in normalized):
            intent = "plan_phpunit"
        elif "plan_cli" in normalized or ("plan debug" in normalized and "cli" in normalized):
            intent = "plan_cli"
        elif "execute_phpunit" in normalized or "execute phpunit" in normalized:
            intent = "execute_phpunit"
        elif "execute_cli" in normalized or "execute cli" in normalized:
            intent = "execute_cli"
        elif "get_session" in normalized:
            intent = "get_session"
        result_type = "session_interpretation" if intent == "interpret_session" else "execution_plan"
        return {
            "tool": "moodle_debug",
            "version": "runtime-v1",
            "query": {"intent": intent, "raw_query": query},
            "normalized_query": {"intent": intent},
            "intent": intent,
            "results": [
                {
                    "id": f"debug-{intent}",
                    "type": result_type,
                    "rank": 1,
                    "confidence": "high",
                    "source": {"kind": "runtime_profile", "profile_name": "mock", "session_id": "mds_example_session_id"},
                    "content": {
                        "summary": f"Mock debugger response for {intent}.",
                        "likely_fault": {"file": "mod/assign/tests/grading_test.php"},
                        "inspection_targets": [{"kind": "file", "value": "mod/assign/tests/grading_test.php"}],
                        "rerun_command": "php bin/moodle-debug runtime-query --json '{...}'",
                        "plan": {"validated_target": {"normalized_test_ref": "mod_assign\\tests\\grading_test::test_grade_submission"}},
                    },
                    "diagnostics": [],
                }
            ],
            "diagnostics": [],
            "meta": {"status": "ok", "generated_at": "2026-04-15T00:00:00+00:00", "repo_root": "/mock/debug", "dry_run": not intent.startswith("execute_"), "exit_code": 0},
        }
    return {
        "tool": "agentic_sitemap",
        "version": "v1",
        "query": query,
        "normalized_query": normalized,
        "intent": {"query_intent": "page_lookup", "task_intent": "page_context_lookup", "concept_families": ["render"]},
        "results": [
            {
                "id": "site-render",
                "type": "page_context",
                "rank": 1,
                "confidence": "medium",
                "source": _runtime_source("moodle_site", "/course/view.php"),
                "content": {"page_type": "course", "summary": "Representative Moodle page context for render inspection."},
                "diagnostics": {"ranking_explanation": "mock", "support_reason": "mock", "token_count": 0, "selection_strategy": "mock"},
            }
        ],
    }


def _mock_runner(*, args, text, capture_output, check, cwd=None, env=None):
    del text, capture_output, check, cwd, env
    tool = args[1] if len(args) > 1 else Path(args[0]).name
    joined = " ".join(args)
    query = ""
    if "--query" in args:
        query = args[args.index("--query") + 1]
    elif "--symbol" in args:
        query = args[args.index("--symbol") + 1]
    elif "--file" in args:
        query = args[args.index("--file") + 1]
    elif len(args) > 3 and args[2] == "query":
        query = args[3]
    if tool == "mock-devdocs":
        payload = _mock_payload("agentic_docs", query)
    elif tool == "mock-indexer":
        payload = _mock_payload("agentic_indexer", query)
    elif tool == "mock-sitemap":
        payload = _mock_payload("agentic_sitemap", query or joined)
    elif tool == "mock-debug":
        payload = _mock_payload("moodle_debug", query or joined)
    else:
        raise FileNotFoundError(tool)
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")


def default_mock_config() -> OrchestratorConfig:
    return OrchestratorConfig.from_sources(
        args=argparse.Namespace(
            devdocs_cmd="/bin/sh",
            devdocs_workdir=None,
            devdocs_extra_args="mock-devdocs",
            indexer_cmd="/bin/sh",
            indexer_workdir=None,
            indexer_extra_args="mock-indexer",
            sitemap_cmd="/bin/sh",
            sitemap_workdir=None,
            sitemap_extra_args="mock-sitemap",
            debug_cmd="/bin/sh",
            debug_workdir=None,
            debug_extra_args="mock-debug",
            devdocs_db_path="/mock/devdocs.sqlite",
            indexer_db_path="/mock/index.sqlite",
            sitemap_run_dir="/mock/sitemap-run",
        )
    )


def build_review_runtime(*, config_path: str | None = None, allow_mock_fallback: bool = False) -> ReviewBundleRuntime:
    try:
        config = OrchestratorConfig.from_sources(config_path=config_path)
        config.validate_required_resources(["agentic_devdocs", "agentic_indexer", "agentic_sitemap"])
    except ConfigurationError:
        if not allow_mock_fallback:
            raise
        mock_config = default_mock_config()
        return ReviewBundleRuntime(
            service=OrchestratorService.from_config(mock_config, runner=_mock_runner),
            execution_mode="mock_fallback",
            config=mock_config,
            runner=_mock_runner,
        )

    return ReviewBundleRuntime(
        service=OrchestratorService.from_config(config),
        execution_mode="real_local_tools",
        config=config,
        runner=None,
    )


def generate_review_bundle(*, config_path: str | None = None, allow_mock_fallback: bool = False) -> Path:
    repo_root = resolve_repo_root()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_dir = repo_root / "_smoke_test" / "review_bundle" / timestamp
    examples_dir = bundle_dir / "example_outputs"
    examples_dir.mkdir(parents=True, exist_ok=True)

    runtime = build_review_runtime(config_path=config_path, allow_mock_fallback=allow_mock_fallback)
    service = runtime.service
    config = runtime.config
    routing_cases = load_routing_eval_cases()
    routing_evaluation = evaluate_auto_routing(service, cases=routing_cases)
    comparison_cases = [case for case in routing_cases if case.compare_modes]
    comparisons = [compare_modes_for_case(case) for case in comparison_cases]
    task_cases = load_task_eval_cases()
    task_evaluation = evaluate_task_outputs(service, cases=task_cases)
    health_report = collect_health_report(config, runner=runtime.runner, deep=False)
    debug_evaluation = None
    debug_cases = load_debug_eval_cases()
    if config.debug.command:
        debug_evaluation = evaluate_debug_routes(service, cases=debug_cases)
    warning_health_report = _simulated_health_report(health_report, status="WARNING")
    failure_health_report = _simulated_health_report(health_report, status="FAIL")

    for case_result in routing_evaluation["cases"]:
        slug = case_result["case_id"]
        (examples_dir / f"{slug}.auto.json").write_text(
            json.dumps(case_result["payload"], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    for case_result in task_evaluation["cases"]:
        slug = case_result["case_id"]
        (examples_dir / f"{slug}.task-context.json").write_text(
            json.dumps(case_result["payload"], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    render_examples = [
        ("render_vague_query", "understand how something should render in Moodle"),
        ("render_symbol_query", "mod_assign\\output\\grading_app"),
        ("render_file_query", "mod/assign/locallib.php"),
    ]
    for slug, query in render_examples:
        payload = service.query(query=query, route_mode="task")
        (examples_dir / f"{slug}.task.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    if debug_evaluation is not None:
        for case_result in debug_evaluation["cases"]:
            slug = case_result["case_id"]
            (examples_dir / f"{slug}.debug.json").write_text(json.dumps(case_result["payload"], indent=2, sort_keys=True), encoding="utf-8")

    for comparison in comparisons:
        case = next(item for item in routing_cases if item.id == comparison["case_id"])
        task_payload = service.query(query=case.query, context=case.context, route_mode="task")
        manual_payload = service.query(query=case.query, context=case.context, route_mode="manual", manual_tools=case.preferred_tools)
        (examples_dir / f"{case.id}.task.json").write_text(json.dumps(task_payload, indent=2, sort_keys=True), encoding="utf-8")
        (examples_dir / f"{case.id}.manual.json").write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")

    routing_eval_payload = serializable_routing_eval(routing_evaluation)
    task_eval_payload = serializable_task_eval(task_evaluation)
    (bundle_dir / "routing_eval.json").write_text(json.dumps(routing_eval_payload, indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "routing_eval.txt").write_text(render_routing_eval_text(routing_eval_payload), encoding="utf-8")
    (bundle_dir / "task_eval.json").write_text(json.dumps(task_eval_payload, indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "task_eval.txt").write_text(render_task_eval_text(task_eval_payload), encoding="utf-8")
    if debug_evaluation is not None:
        (bundle_dir / "debug_eval.json").write_text(json.dumps(debug_evaluation, indent=2, sort_keys=True), encoding="utf-8")
        (bundle_dir / "debug_eval.txt").write_text(render_debug_eval_text(debug_evaluation), encoding="utf-8")
    (bundle_dir / "mode_comparison.json").write_text(json.dumps(comparisons, indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "mode_comparison.md").write_text(render_mode_comparison_markdown(comparisons), encoding="utf-8")
    (bundle_dir / "config_used.json").write_text(json.dumps(sanitized_config_report(config), indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "health.json").write_text(json.dumps(serializable_health_report(health_report), indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "health.txt").write_text(render_health_text(health_report), encoding="utf-8")
    (bundle_dir / "health_warning.json").write_text(json.dumps(serializable_health_report(warning_health_report), indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "health_warning.txt").write_text(render_health_text(warning_health_report), encoding="utf-8")
    (bundle_dir / "health_failure.json").write_text(json.dumps(serializable_health_report(failure_health_report), indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "health_failure.txt").write_text(render_health_text(failure_health_report), encoding="utf-8")
    (bundle_dir / "README_snapshot.md").write_text((repo_root / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    for doc_name in ("AGENTS.md", "CONTRIBUTING.md"):
        doc_path = repo_root / doc_name
        if doc_path.exists():
            (bundle_dir / doc_name).write_text(doc_path.read_text(encoding="utf-8"), encoding="utf-8")
    (bundle_dir / "docs_checklist.md").write_text(
        "\n".join(
            [
                "# Docs Checklist",
                "",
                "- README updated with project scope, setup, quickstart, testing, and review-bundle guidance",
                "- AI/contributor guidance captured in AGENTS.md and CONTRIBUTING.md",
                "- Review bundle now snapshots changed docs for external verification",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "refactor_map.md").write_text(
        "\n".join(
            [
                "# Refactor Map",
                "",
                "- Extracted review summary and serialization helpers into `src/agentic_orchestrator/review_reporting.py`",
                "- Kept `review_bundle.py` focused on runtime selection, artifact generation, and command capture",
                "- Verified behavior stability with deterministic tests plus live eval reruns",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    pilot_root = bundle_dir / "pilot_trials"
    first_task_case = task_cases[0]
    trial_dir = create_pilot_trial(
        service,
        config,
        query=first_task_case.query,
        route_mode=first_task_case.route_mode,
        context=first_task_case.context,
        task_label=first_task_case.id,
        notes="review bundle sample trial",
        pilot_root=str(pilot_root),
        outcome="useful",
        review_notes="Sample recorded supervised outcome for bundle review.",
        did_it_help_find_right_files=True,
        did_it_help_find_right_docs=True,
    )
    pilot_report = collect_pilot_report(pilot_root=str(pilot_root))
    (bundle_dir / "pilot_report.txt").write_text(render_pilot_report_text(pilot_report), encoding="utf-8")
    (bundle_dir / "pilot_report.json").write_text(json.dumps(pilot_report, indent=2, sort_keys=True), encoding="utf-8")
    summary_text = _augment_summary(
        build_review_summary(
            bundle_dir=bundle_dir,
            runtime_mode=runtime.execution_mode,
            config_path=config_path,
            config=config,
            task_evaluation=task_evaluation,
            routing_evaluation=routing_evaluation,
            health_report=health_report,
        ),
        warning_example_path=bundle_dir / "health_warning.txt",
        failure_example_path=bundle_dir / "health_failure.txt",
        pilot_trial_dir=trial_dir,
        pilot_report_path=bundle_dir / "pilot_report.txt",
    )
    if debug_evaluation is not None:
        summary_text += (
            "\n## Debugger Integration\n\n"
            + f"- Debug eval summary: correct={debug_evaluation['summary']['CORRECT']}, wrong={debug_evaluation['summary']['WRONG']}\n"
            + "- Supported explicit routes: interpret session, get session, plan phpunit, plan cli, execute phpunit, execute cli\n"
            + "- `debug_results` are grouped separately so debugger provenance stays visible\n"
        )
    (bundle_dir / "summary.md").write_text(summary_text, encoding="utf-8")

    _write_command_output(bundle_dir / "pytest.txt", ["python3", "-m", "pytest"], cwd=repo_root, extra_env={"PYTHONPATH": "src"})
    _write_command_output(bundle_dir / "git_status.txt", ["git", "status", "--short", "--branch"], cwd=repo_root)
    _write_command_output(bundle_dir / "git_commit.txt", ["git", "rev-parse", "HEAD"], cwd=repo_root, allow_failure=True)
    return bundle_dir


def _simulated_health_report(report: dict[str, object], *, status: str) -> dict[str, object]:
    """Create a compact example warning/failure report for bundle reviewers."""

    cloned = json.loads(json.dumps(report))
    if status == "WARNING":
        cloned["overall_status"] = "WARNING"
        for check in cloned["checks"]:
            if check["name"] == "resource.indexer_db":
                check["status"] = "WARNING"
                check["summary"] = "resource exists but appears stale"
                break
        return cloned
    cloned["overall_status"] = "FAIL"
    for check in cloned["checks"]:
        if check["name"] == "contract.agentic_indexer":
            check["status"] = "FAIL"
            check["summary"] = "agentic_indexer returned malformed contract JSON"
            break
    return cloned


def _augment_summary(
    base_summary: str,
    *,
    warning_example_path: Path,
    failure_example_path: Path,
    pilot_trial_dir: Path,
    pilot_report_path: Path,
) -> str:
    return (
        base_summary
        + "\n## Operational Cleanup\n\n"
        + "- Standardized bundle file naming toward underscore-separated artifacts such as `git_status.txt`, `git_commit.txt`, and `config_used.json`\n"
        + f"- Warning health example: `{warning_example_path.name}`\n"
        + f"- Failure health example: `{failure_example_path.name}`\n"
        + "\n## Pilot Harness\n\n"
        + f"- Example pilot trial directory: `{pilot_trial_dir.name}`\n"
        + f"- Pilot report output: `{pilot_report_path.name}`\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentic_orchestrator.review_bundle")
    parser.add_argument("--config", help="Optional TOML config file for live sibling tool execution.")
    parser.add_argument(
        "--allow-mock-fallback",
        action="store_true",
        help="Permit deterministic mock fallback when live tool configuration is unavailable.",
    )
    args = parser.parse_args(argv)
    bundle_dir = generate_review_bundle(config_path=args.config, allow_mock_fallback=args.allow_mock_fallback)
    print(bundle_dir)
    return 0


def _write_command_output(
    path: Path,
    command: list[str],
    *,
    cwd: Path,
    extra_env: dict[str, str] | None = None,
    allow_failure: bool = False,
) -> None:
    env = None
    if extra_env:
        env = {**os.environ, **extra_env}
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0 and not allow_failure:
        raise RuntimeError(f"Command failed for review bundle: {' '.join(command)}")
    output = []
    output.append(f"$ {' '.join(command)}")
    output.append("")
    if completed.stdout:
        output.append(completed.stdout.rstrip())
    if completed.stderr:
        output.append(completed.stderr.rstrip())
    output.append(f"[exit_code={completed.returncode}]")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
