# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.orchestrator import OrchestratorService


def _payload(tool: str, query: str, file_value: str) -> dict:
    if tool == "agentic_docs":
        render_like = "renderer" in file_value or "mustache" in file_value
        return {
            "tool": tool,
            "version": "v1",
            "query": query,
            "normalized_query": query.lower(),
            "intent": {},
            "results": [
                {
                    "id": "docs-1",
                    "type": "knowledge_bundle",
                    "rank": 1,
                    "confidence": "high",
                    "source": {
                        "name": "docs",
                        "type": "documentation",
                    "url": None,
                    "canonical_url": None,
                    "path": "docs/example.md",
                    "document_title": "Output API" if render_like else None,
                    "section_title": "Renderable" if render_like else None,
                    "heading_path": ["Page Output Journey", "Renderable"] if render_like else [],
                },
                    "content": {"summary": "Docs summary", "file_anchors": [file_value]},
                    "diagnostics": {},
                }
            ],
        }
    if tool == "agentic_indexer":
        return {
            "tool": tool,
            "version": "v1",
            "query": query,
            "normalized_query": query.lower(),
            "intent": {},
            "results": [
                {
                    "id": "code-1",
                    "type": "context_bundle",
                    "rank": 1,
                    "confidence": "high",
                    "source": {
                        "name": "index",
                        "type": "code_index",
                        "url": None,
                        "canonical_url": None,
                        "path": file_value,
                        "document_title": None,
                        "section_title": None,
                        "heading_path": [],
                    },
                    "content": {"path": file_value, "symbol": "mod_example\\thing", "summary": "Code summary"},
                    "diagnostics": {},
                }
            ],
        }
    if tool == "moodle_debug":
        intent = "interpret_session"
        if "phpunit" in query.lower() and "execute" in query.lower():
            intent = "execute_phpunit"
        elif "phpunit" in query.lower():
            intent = "plan_phpunit"
        elif "cli" in query.lower() and "execute" in query.lower():
            intent = "execute_cli"
        elif "cli" in query.lower():
            intent = "plan_cli"
        return {
            "tool": "moodle_debug",
            "version": "runtime-v1",
            "query": {"intent": intent, "raw_query": query},
            "normalized_query": {"intent": intent},
            "intent": intent,
            "results": [
                {
                    "id": "debug-1",
                    "type": "execution_plan" if intent.startswith(("plan_", "execute_")) else "session_interpretation",
                    "rank": 1,
                    "confidence": "high",
                    "source": {"kind": "runtime_profile", "profile_name": "mock", "session_id": "mds_example_session_id"},
                    "content": {
                        "summary": "Debug summary",
                        "plan": {
                            "validated_target": {
                                "normalized_test_ref": "mod_assign\\tests\\grading_test::test_grade_submission",
                                "script_path": "admin/cli/some_script.php",
                            },
                            "execution": {"command": ["php", "vendor/bin/phpunit"]},
                        },
                        "likely_fault": {"file": "mod/assign/tests/grading_test.php"},
                        "inspection_targets": [{"kind": "file", "value": "mod/assign/tests/grading_test.php"}],
                        "rerun_command": "php bin/moodle-debug runtime-query --json '{...}'",
                    },
                    "diagnostics": [],
                }
            ],
            "diagnostics": [],
            "meta": {"status": "ok", "generated_at": "2026-04-15T00:00:00+00:00", "repo_root": "/tmp/debug", "dry_run": not intent.startswith("execute_"), "exit_code": 0},
        }
    return {
        "tool": tool,
        "version": "v1",
        "query": query,
        "normalized_query": query.lower(),
        "intent": {},
        "results": [
            {
                "id": "site-1",
                "type": "page_context",
                "rank": 1,
                "confidence": "medium",
                "source": {
                    "name": "site",
                    "type": "site_manifest",
                    "url": None,
                    "canonical_url": None,
                    "path": "/course/view.php",
                    "document_title": None,
                    "section_title": None,
                    "heading_path": [],
                },
                "content": {"page_type": "course", "summary": "Site summary"},
                "diagnostics": {},
            }
        ],
    }


def _runner(*, args, text, capture_output, check, cwd=None, env=None):
    del text, capture_output, check, cwd, env
    tool_tag = args[1]
    if tool_tag == "mock-devdocs":
        anchor = "admin/tool/demo/classes/output/renderer.php" if "render" in args[3].lower() else "settings.php"
        payload = _payload("agentic_docs", args[3], anchor)
    elif tool_tag == "mock-indexer":
        if "--file" in args:
            query = args[args.index("--file") + 1]
            file_value = query
        elif "--query" in args:
            query = args[args.index("--query") + 1]
            file_value = "admin/tool/demo/settings.php"
        else:
            query = args[args.index("--symbol") + 1]
            file_value = "mod/assign/classes/output/grading_app.php"
        payload = _payload("agentic_indexer", query, file_value)
    elif tool_tag == "mock-debug":
        query = args[args.index("--json") + 1]
        payload = _payload("moodle_debug", query, "")
    else:
        payload = _payload("agentic_sitemap", args[args.index("--query") + 1], "/course/view.php")
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")


def _config() -> OrchestratorConfig:
    executable = "/bin/sh"
    return OrchestratorConfig.from_args(
        Namespace(
            config=None,
            devdocs_cmd=executable,
            devdocs_workdir=None,
            devdocs_extra_args="mock-devdocs",
            indexer_cmd=executable,
            indexer_workdir=None,
            indexer_extra_args="mock-indexer",
            sitemap_cmd=executable,
            sitemap_workdir=None,
            sitemap_extra_args="mock-sitemap",
            debug_cmd=executable,
            debug_workdir=None,
            debug_extra_args="mock-debug",
            devdocs_db_path="/tmp/devdocs.sqlite",
            indexer_db_path="/tmp/index.sqlite",
            sitemap_run_dir="/tmp/sitemap-run",
        )
    )


def test_orchestrator_merges_grouped_results_and_preserves_tool_boundaries() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="add admin settings to a plugin", route_mode="task")
    result = payload["results"][0]
    assert payload["tool"] == "agentic_orchestrator"
    assert result["type"] == "orchestrated_context"
    assert len(result["content"]["docs_results"]) == 1
    assert len(result["content"]["code_results"]) == 1
    assert result["content"]["site_results"] == []
    assert result["content"]["key_signals"]
    assert result["content"]["key_signals"][0]["source_tool"] == "agentic_devdocs"
    assert payload["intent"]["route_mode"] == "task"
    assert result["diagnostics"]["tools_called"][0]["tool"] == "agentic_devdocs"
    assert result["diagnostics"]["route_mode"] == "task"
    assert "selected_tools" in result["diagnostics"]
    assert "routing_reasons" in result["diagnostics"]
    assert "matched_route_signals" in result["diagnostics"]
    assert "assembly_notes" in result["diagnostics"]
    assert result["content"]["result_thin"] is False
    assert result["content"]["refine_query_suggested"] is False


def test_orchestrator_manual_mode_uses_requested_tools() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(
        query="How should this render in Moodle?",
        route_mode="manual",
        manual_tools=["agentic_indexer", "agentic_sitemap"],
        context={"site_lookup": {"mode": "page_type", "query": "dashboard"}},
    )
    result = payload["results"][0]
    assert result["content"]["docs_results"] == []
    assert len(result["content"]["code_results"]) == 1
    assert len(result["content"]["site_results"]) == 1
    assert payload["intent"]["manual_tools"] == ["agentic_indexer", "agentic_sitemap"]


def test_orchestrator_output_is_deterministic_for_same_inputs() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    first = service.query(query="define a web service", route_mode="task")
    second = service.query(query="define a web service", route_mode="task")
    assert first == second


def test_orchestrator_auto_mode_uses_broader_routing_rules() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="Where do Behat feature files go?", route_mode="auto")
    called = [item["tool"] for item in payload["results"][0]["diagnostics"]["tools_called"]]
    assert called == ["agentic_devdocs", "agentic_indexer"]


def test_orchestrator_filters_noisy_external_doc_anchors_from_promoted_evidence() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="add admin settings to a plugin", route_mode="task")
    values = [item["value"] for item in payload["results"][0]["content"]["suggested_next_steps"]]
    assert all("://" not in value for value in values)
    assert all(not value.startswith("//") for value in values)


def test_orchestrator_shapes_vague_render_query_into_docs_anchor_for_indexer() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="understand how something should render in Moodle", route_mode="task")
    result = payload["results"][0]
    shaped = result["diagnostics"]["shaped_queries"]
    assert result["diagnostics"]["query_shaping_applied"] is True
    assert shaped[0]["shaped_query"] == "renderer output mustache template renderable"
    assert result["diagnostics"]["code_signal_source"] == "source_path"
    assert any(step["source_tool"] == "agentic_indexer" for step in result["content"]["suggested_next_steps"])


def test_orchestrator_flags_thin_code_result_with_refine_hints() -> None:
    def thin_runner(*, args, text, capture_output, check, cwd=None, env=None):
        del text, capture_output, check, cwd, env
        if args[1] == "mock-indexer":
            payload = {
                "tool": "agentic_indexer",
                "version": "v1",
                "query": "how does this render",
                "normalized_query": "how does this render",
                "intent": {},
                "results": [
                    {
                        "id": "code-thin",
                        "type": "context_bundle",
                        "rank": 1,
                        "confidence": "medium",
                        "source": {
                            "name": "index",
                            "type": "code_index",
                            "url": None,
                            "canonical_url": None,
                            "path": None,
                            "document_title": None,
                            "section_title": None,
                            "heading_path": [],
                        },
                        "content": {"summary": "Thin code result"},
                        "diagnostics": {},
                    }
                ],
            }
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")
        return _runner(args=args, text=True, capture_output=True, check=False)

    service = OrchestratorService.from_config(_config(), runner=thin_runner)
    payload = service.query(query="How should this render in Moodle?", route_mode="manual", manual_tools=["agentic_indexer"])
    content = payload["results"][0]["content"]
    diagnostics = payload["results"][0]["diagnostics"]
    assert content["result_thin"] is True
    assert "code_anchor" in content["missing_key_signals"]
    assert content["refine_query_suggested"] is True
    assert "specify a symbol" in content["refine_query_hints"]
    assert diagnostics["thin_result"] is True


def test_orchestrator_routes_render_symbol_query_directly_to_indexer_context_bundle() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="mod_assign\\output\\grading_app", route_mode="task")
    result = payload["results"][0]
    called = result["diagnostics"]["tools_called"]
    assert [item["tool"] for item in called] == ["agentic_indexer"]
    assert called[0]["mode"] == "build-context-bundle"
    assert result["content"]["code_results"][0]["source"]["path"] == "mod/assign/classes/output/grading_app.php"


def test_orchestrator_balances_render_next_steps_across_tools() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(query="understand how something should render in Moodle", route_mode="task")
    steps = payload["results"][0]["content"]["suggested_next_steps"]
    sources = {step["source_tool"] for step in steps}
    assert "agentic_devdocs" in sources
    assert "agentic_indexer" in sources
    assert "agentic_sitemap" in sources


def test_orchestrator_groups_debug_results_separately_and_preserves_boundary() -> None:
    service = OrchestratorService.from_config(_config(), runner=_runner)
    payload = service.query(
        query="plan debug for this PHPUnit selector mod_assign\\tests\\grading_test::test_grade_submission",
        route_mode="task",
    )
    result = payload["results"][0]
    assert result["content"]["docs_results"] == []
    assert result["content"]["code_results"] == []
    assert result["content"]["site_results"] == []
    assert len(result["content"]["debug_results"]) == 1
    assert result["diagnostics"]["debug_intent"] == "plan_phpunit"
    assert result["diagnostics"]["debug_execution_mode"] == "safe"
    assert any(step["source_tool"] == "agentic_debug" for step in result["content"]["suggested_next_steps"])
