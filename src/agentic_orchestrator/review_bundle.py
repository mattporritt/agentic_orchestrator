"""Generate a review artifact bundle for the thin prototype."""

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
    bundle_dir.mkdir(parents=True, exist_ok=True)

    runtime = build_review_runtime(config_path=config_path, allow_mock_fallback=allow_mock_fallback)
    service = runtime.service
    config = runtime.config

    examples = {
        "admin_settings": {
            "query": "add admin settings to a plugin",
            "context": {},
            "route_mode": "task",
            "manual_tools": [],
        },
        "scheduled_task": {
            "query": "register a scheduled task",
            "context": {},
            "route_mode": "task",
            "manual_tools": [],
        },
        "web_service": {
            "query": "define a web service",
            "context": {},
            "route_mode": "task",
            "manual_tools": [],
        },
        "privacy_metadata": {
            "query": "add privacy metadata",
            "context": {},
            "route_mode": "task",
            "manual_tools": [],
        },
        "render_ui": {
            "query": "How should this render in Moodle?",
            "context": {"site_lookup": {"mode": "page_type", "query": "dashboard"}},
            "route_mode": "task",
            "manual_tools": [],
        },
    }

    routing_lines: list[str] = ["# Routing Report", ""]
    summary_lines: list[str] = [
        "# Review Summary",
        "",
        "## What The Orchestrator Does",
        "",
        "- Accepts a task query and optional lightweight context",
        "- Applies explicit routing modes to the three runtime-facing tools",
        "- Calls each selected tool via subprocess JSON-contract mode",
        "- Validates the shared outer envelope shape",
        "- Merges tool results into grouped docs/code/site sections",
        "- Emits deterministic suggested next steps grounded in returned evidence",
        "",
        "## Runtime Mode",
        "",
        f"- Review bundle execution mode: `{runtime.execution_mode}`",
        f"- Config path: `{config_path or config.config_path or '(none)'}`",
        "",
        "## Example Execution",
        "",
    ]

    for slug, item in examples.items():
        payload = service.query(
            query=item["query"],
            context=item["context"],
            route_mode=item["route_mode"],
            manual_tools=item["manual_tools"],
        )
        (bundle_dir / f"{slug}.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        result = payload["results"][0]
        tools = ", ".join(call["tool"] for call in result["diagnostics"]["tools_called"])
        routing_lines.append(f"- `{slug}`: mode={payload['intent']['route_mode']} tools={tools}")
        summary_lines.append(f"- `{slug}` used `{runtime.execution_mode}` and called: {tools}")

    summary_lines.extend(
        [
            "",
            "## Merged Result Structure",
            "",
            "- `docs_results` preserve original devdocs contract results",
            "- `code_results` preserve original indexer contract results",
            "- `site_results` preserve original sitemap contract results",
            "- `suggested_next_steps` are derived deterministically from returned provenance",
            "- `diagnostics.tools_called` records which tools ran and why",
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
            "## Intentionally Out Of Scope",
            "",
            "- Autonomous planning",
            "- Code modification or execution",
            "- LLM calls",
            "- APIs, services, or persistent orchestration state",
            "",
            f"Review artifact bundle path: {bundle_dir}",
        ]
    )

    (bundle_dir / "routing-report.md").write_text("\n".join(routing_lines) + "\n", encoding="utf-8")
    (bundle_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    (bundle_dir / "config-used.json").write_text(json.dumps(_sanitized_config_report(config), indent=2, sort_keys=True), encoding="utf-8")
    _write_command_output(bundle_dir / "pytest.txt", ["python3", "-m", "pytest"], cwd=repo_root, extra_env={"PYTHONPATH": "src"})
    _write_command_output(bundle_dir / "git-status.txt", ["git", "status", "--short", "--branch"], cwd=repo_root)
    _write_command_output(bundle_dir / "git-commit.txt", ["git", "rev-parse", "HEAD"], cwd=repo_root, allow_failure=True)
    return bundle_dir


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
