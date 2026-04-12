"""Generate a deterministic review artifact bundle for the thin prototype."""

from __future__ import annotations

import json
import os
import subprocess
from argparse import Namespace
from datetime import datetime
from pathlib import Path

from agentic_orchestrator.config import OrchestratorConfig, resolve_repo_root
from agentic_orchestrator.orchestrator import OrchestratorService


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


def _mock_runner(*, args, text, capture_output, check):
    tool = Path(args[0]).name
    joined = " ".join(args)
    query = ""
    if "--query" in args:
        query = args[args.index("--query") + 1]
    elif "--symbol" in args:
        query = args[args.index("--symbol") + 1]
    elif len(args) > 2 and args[1] == "query":
        query = args[2]
    if tool == "mock-devdocs":
        payload = _mock_payload("agentic_docs", query)
    elif tool == "mock-indexer":
        payload = _mock_payload("agentic_indexer", query)
    elif tool == "mock-sitemap":
        payload = _mock_payload("agentic_sitemap", query or joined)
    else:
        raise FileNotFoundError(tool)
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")


def generate_review_bundle() -> Path:
    repo_root = resolve_repo_root()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_dir = repo_root / "_smoke_test" / "review_bundle" / timestamp
    bundle_dir.mkdir(parents=True, exist_ok=True)

    config = OrchestratorConfig.from_args(
        Namespace(
            devdocs_cmd="mock-devdocs",
            indexer_cmd="mock-indexer",
            sitemap_cmd="mock-sitemap",
            devdocs_db_path="/mock/devdocs.sqlite",
            indexer_db_path="/mock/index.sqlite",
            sitemap_run_dir="/mock/sitemap-run",
        )
    )
    service = OrchestratorService.from_config(config, runner=_mock_runner)

    examples = {
        "admin_settings": ("add admin settings to a plugin", {}),
        "scheduled_task": ("register a scheduled task", {}),
        "web_service": ("define a web service", {}),
        "privacy_metadata": ("add privacy metadata", {}),
        "render_ui": ("How should this render in Moodle?", {"site_lookup": {"mode": "page", "query": "course"}}),
    }
    routing_lines: list[str] = ["# Routing Report", ""]
    for slug, (query, context) in examples.items():
        payload = service.query(query=query, context=context)
        (bundle_dir / f"{slug}.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        result = payload["results"][0]
        tools = ", ".join(call["tool"] for call in result["diagnostics"]["tools_called"])
        routing_lines.append(f"- `{slug}`: {tools}")

    (bundle_dir / "routing-report.md").write_text("\n".join(routing_lines) + "\n", encoding="utf-8")
    (bundle_dir / "config.example.toml").write_text((repo_root / "config.example.toml").read_text(encoding="utf-8"), encoding="utf-8")
    _write_command_output(bundle_dir / "pytest.txt", ["python3", "-m", "pytest"], cwd=repo_root, extra_env={"PYTHONPATH": "src"})
    _write_command_output(bundle_dir / "git-status.txt", ["git", "status", "--short", "--branch"], cwd=repo_root)
    _write_command_output(bundle_dir / "git-commit.txt", ["git", "rev-parse", "HEAD"], cwd=repo_root, allow_failure=True)

    summary = [
        "# Review Summary",
        "",
        "## What The Orchestrator Does",
        "",
        "- Accepts a task query and optional lightweight context",
        "- Applies explicit rule-based routing to the three runtime-facing tools",
        "- Calls each selected tool via subprocess JSON-contract mode",
        "- Validates the shared outer envelope shape",
        "- Merges tool results into grouped docs/code/site sections",
        "- Emits deterministic suggested next steps grounded in returned evidence",
        "",
        "## Example Tool Routing",
        "",
        "- Admin settings: devdocs + indexer",
        "- Scheduled task: devdocs + indexer",
        "- Web service: devdocs + indexer",
        "- Privacy metadata: devdocs + indexer",
        "- Render/UI: devdocs + indexer + sitemap",
        "",
        "## Merged Result Structure",
        "",
        "- `docs_results` preserve original devdocs contract results",
        "- `code_results` preserve original indexer contract results",
        "- `site_results` preserve original sitemap contract results",
        "- `suggested_next_steps` are derived deterministically from returned provenance",
        "- `diagnostics.tools_called` records which tools ran and why",
        "",
        "## Intentionally Out Of Scope",
        "",
        "- Autonomous planning",
        "- Code modification or execution",
        "- LLM calls",
        "- APIs, services, or persistent orchestration state",
        "",
        "## Notes",
        "",
        "- Example outputs in this bundle are generated with deterministic mock tool responders because the sibling tool dependencies are not installed in this workspace by default.",
        "- Unit tests still exercise the subprocess adapter and contract-validation boundaries directly.",
        "",
        f"Review artifact bundle path: {bundle_dir}",
    ]
    (bundle_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return bundle_dir


def main() -> int:
    bundle_dir = generate_review_bundle()
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
