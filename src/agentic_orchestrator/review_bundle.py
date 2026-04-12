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
from agentic_orchestrator.errors import ConfigurationError
from agentic_orchestrator.orchestrator import OrchestratorService
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
    elif len(args) > 3 and args[2] == "query":
        query = args[3]
    if tool == "mock-devdocs":
        payload = _mock_payload("agentic_docs", query)
    elif tool == "mock-indexer":
        payload = _mock_payload("agentic_indexer", query)
    elif tool == "mock-sitemap":
        payload = _mock_payload("agentic_sitemap", query or joined)
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
        )

    return ReviewBundleRuntime(
        service=OrchestratorService.from_config(config),
        execution_mode="real_local_tools",
        config=config,
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

    for comparison in comparisons:
        case = next(item for item in routing_cases if item.id == comparison["case_id"])
        task_payload = service.query(query=case.query, context=case.context, route_mode="task")
        manual_payload = service.query(query=case.query, context=case.context, route_mode="manual", manual_tools=case.preferred_tools)
        (examples_dir / f"{case.id}.task.json").write_text(json.dumps(task_payload, indent=2, sort_keys=True), encoding="utf-8")
        (examples_dir / f"{case.id}.manual.json").write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")

    (bundle_dir / "routing_eval.json").write_text(json.dumps(_serializable_eval(routing_evaluation), indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "routing_eval.txt").write_text(render_routing_eval_text(_serializable_eval(routing_evaluation)), encoding="utf-8")
    (bundle_dir / "task_eval.json").write_text(json.dumps(_serializable_task_eval(task_evaluation), indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "task_eval.txt").write_text(render_task_eval_text(_serializable_task_eval(task_evaluation)), encoding="utf-8")
    (bundle_dir / "mode_comparison.json").write_text(json.dumps(comparisons, indent=2, sort_keys=True), encoding="utf-8")
    (bundle_dir / "mode_comparison.md").write_text(_render_mode_comparison_markdown(comparisons), encoding="utf-8")
    (bundle_dir / "config-used.json").write_text(json.dumps(_sanitized_config_report(config), indent=2, sort_keys=True), encoding="utf-8")

    task_weak_cases = [case for case in task_evaluation["cases"] if case["status"] != "COMPLETE"]
    summary_lines = [
        "# Task Review Summary",
        "",
        "## Runtime Mode",
        "",
        f"- Review bundle execution mode: `{runtime.execution_mode}`",
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
        "## Assembly Changes",
        "",
        "- Promoted compact `key_signals` so the best doc, code, and site evidence is visible without flattening tool boundaries",
        "- Improved `suggested_next_steps` to extract nested code paths and symbols from indexer bundles instead of only top-level fields",
        "- Filtered noisy external or relative-path anchors from promoted evidence so next steps stay more actionable",
        "- Kept grouped `docs_results`, `code_results`, and `site_results` intact underneath the promoted evidence",
        "",
        "## Task Results",
        "",
        f"- complete: {task_evaluation['summary']['COMPLETE']}",
        f"- partial: {task_evaluation['summary']['PARTIAL']}",
        f"- insufficient: {task_evaluation['summary']['INSUFFICIENT']}",
        "",
        "## Representative Task Cases",
        "",
    ]
    for case in task_evaluation["cases"]:
        summary_lines.append(
            f"- `{case['case_id']}`: {case['status']} -> tools={', '.join(case['selected_tools'])}; present={', '.join(case['key_signals_present']) or '(none)'}"
        )
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
            "## Routing Stability",
            "",
            f"- current routing baseline: correct={routing_evaluation['summary']['CORRECT']}, acceptable={routing_evaluation['summary']['ACCEPTABLE']}, overcalled={routing_evaluation['summary']['OVERCALLED']}, undercalled={routing_evaluation['summary']['UNDERCALLED']}, wrong={routing_evaluation['summary']['WRONG']}",
            "- This phase did not intentionally broaden routing; the main changes were in assembly and promoted evidence",
            "",
            "## Remaining Limitations",
            "",
            "- Task evaluation still grades deterministic signal coverage rather than semantic answer quality",
            "- Some sibling-tool results remain inherently thin, especially when indexer free-text bundles do not return a strong primary context",
            "- The orchestrator still assembles evidence; it does not plan edits or decide implementation steps",
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
    (bundle_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    _write_command_output(bundle_dir / "pytest.txt", ["python3", "-m", "pytest"], cwd=repo_root, extra_env={"PYTHONPATH": "src"})
    _write_command_output(bundle_dir / "git-status.txt", ["git", "status", "--short", "--branch"], cwd=repo_root)
    _write_command_output(bundle_dir / "git-commit.txt", ["git", "rev-parse", "HEAD"], cwd=repo_root, allow_failure=True)
    return bundle_dir


def _serializable_eval(evaluation: dict[str, object]) -> dict[str, object]:
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


def _serializable_task_eval(evaluation: dict[str, object]) -> dict[str, object]:
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


def _render_mode_comparison_markdown(comparisons: list[dict[str, object]]) -> str:
    lines = ["# Mode Comparison", ""]
    for item in comparisons:
        lines.append(f"- `{item['case_id']}`")
        lines.append(f"  task: {', '.join(item['task_tools'])}")
        lines.append(f"  auto: {', '.join(item['auto_tools'])}")
        lines.append(f"  manual: {', '.join(item['manual_tools'])}")
    return "\n".join(lines) + "\n"


def _sanitized_config_report(config: OrchestratorConfig) -> dict[str, object]:
    return {
        "config_path": config.config_path,
        "tools": config.tool_path_report(),
        "resources": {
            "devdocs_db_path": config.devdocs_db_path,
            "indexer_db_path": config.indexer_db_path,
            "sitemap_run_dir": config.sitemap_run_dir,
        },
    }


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
