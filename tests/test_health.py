from __future__ import annotations

import json
import os
import subprocess
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.health import collect_health_report, render_health_text


def _tool_script(path: Path) -> str:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def _config(tmp_path: Path) -> OrchestratorConfig:
    tool = _tool_script(tmp_path / "tool")
    docs_db = tmp_path / "docs.sqlite"
    docs_db.write_text("docs", encoding="utf-8")
    index_db = tmp_path / "index.sqlite"
    index_db.write_text("index", encoding="utf-8")
    sitemap_run = tmp_path / "sitemap-run"
    sitemap_run.mkdir()
    (sitemap_run / "manifest.json").write_text("{}", encoding="utf-8")
    return OrchestratorConfig.from_args(
        Namespace(
            config=None,
            devdocs_cmd=tool,
            devdocs_workdir=None,
            devdocs_extra_args=None,
            indexer_cmd=tool,
            indexer_workdir=None,
            indexer_extra_args=None,
            sitemap_cmd=tool,
            sitemap_workdir=None,
            sitemap_extra_args=None,
            devdocs_db_path=str(docs_db),
            indexer_db_path=str(index_db),
            sitemap_run_dir=str(sitemap_run),
        )
    )


def _runner_for_contracts(*, args, text, capture_output, check, cwd=None, env=None):
    del text, capture_output, check, cwd, env
    command = Path(args[0]).name
    subcommand = args[1] if len(args) > 1 else ""
    query = ""
    if "--query" in args:
        query = args[args.index("--query") + 1]
    elif "--symbol" in args:
        query = args[args.index("--symbol") + 1]
    payload_tool = "agentic_sitemap"
    if subcommand == "query":
        payload_tool = "agentic_docs"
        query = args[2]
    elif command == "tool" and subcommand in {"build-context-bundle", "find-definition", "semantic-context"}:
        payload_tool = "agentic_indexer"
    payload = {
        "tool": payload_tool,
        "version": "v1",
        "query": query,
        "normalized_query": query.lower(),
        "intent": {},
        "results": [],
    }
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")


def test_collect_health_report_marks_missing_tool_as_fail(tmp_path: Path) -> None:
    config = _config(tmp_path)
    broken = config.devdocs.command[0] + ".missing"
    broken_config = OrchestratorConfig.from_args(
        Namespace(
            config=None,
            devdocs_cmd=broken,
            devdocs_workdir=None,
            devdocs_extra_args=None,
            indexer_cmd=config.indexer.command[0],
            indexer_workdir=None,
            indexer_extra_args=None,
            sitemap_cmd=config.sitemap.command[0],
            sitemap_workdir=None,
            sitemap_extra_args=None,
            devdocs_db_path=config.devdocs_db_path,
            indexer_db_path=config.indexer_db_path,
            sitemap_run_dir=config.sitemap_run_dir,
        )
    )
    report = collect_health_report(broken_config, runner=_runner_for_contracts)
    checks = {check["name"]: check for check in report["checks"]}
    assert report["overall_status"] == "FAIL"
    assert checks["tool.agentic_devdocs"]["status"] == "FAIL"


def test_collect_health_report_marks_missing_resource_as_fail(tmp_path: Path) -> None:
    config = _config(tmp_path)
    report = collect_health_report(
        OrchestratorConfig.from_args(
            Namespace(
                config=None,
                devdocs_cmd=config.devdocs.command[0],
                devdocs_workdir=None,
                devdocs_extra_args=None,
                indexer_cmd=config.indexer.command[0],
                indexer_workdir=None,
                indexer_extra_args=None,
                sitemap_cmd=config.sitemap.command[0],
                sitemap_workdir=None,
                sitemap_extra_args=None,
                devdocs_db_path=None,
                indexer_db_path=config.indexer_db_path,
                sitemap_run_dir=config.sitemap_run_dir,
            )
        ),
        runner=_runner_for_contracts,
    )
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["resource.devdocs_db"]["status"] == "FAIL"
    assert "not configured" in checks["resource.devdocs_db"]["summary"]


def test_collect_health_report_marks_stale_resource_as_warning(tmp_path: Path) -> None:
    config = _config(tmp_path)
    old_time = datetime.now(UTC) - timedelta(days=60)
    os.utime(config.devdocs_db_path, (old_time.timestamp(), old_time.timestamp()))
    report = collect_health_report(config, runner=_runner_for_contracts, now=datetime.now(UTC))
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["resource.devdocs_db"]["status"] == "WARNING"
    assert checks["resource.devdocs_db"]["details"]["age_hours"] > checks["resource.devdocs_db"]["details"]["max_age_hours"]


def test_collect_health_report_returns_ok_for_healthy_configuration(tmp_path: Path) -> None:
    config = _config(tmp_path)
    report = collect_health_report(config, runner=_runner_for_contracts)
    checks = {check["name"]: check for check in report["checks"]}
    assert report["overall_status"] == "OK"
    assert checks["tool.agentic_devdocs"]["status"] == "OK"
    assert checks["contract.agentic_indexer"]["status"] == "OK"


def test_collect_health_report_marks_contract_failure_as_fail(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def bad_runner(*, args, text, capture_output, check, cwd=None, env=None):
        del text, capture_output, check, cwd, env
        if "build-context-bundle" in args:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="{broken", stderr="")
        return _runner_for_contracts(args=args, text=True, capture_output=True, check=False)

    report = collect_health_report(config, runner=bad_runner)
    checks = {check["name"]: check for check in report["checks"]}
    assert report["overall_status"] == "FAIL"
    assert checks["contract.agentic_indexer"]["status"] == "FAIL"
    assert "invalid JSON" in checks["contract.agentic_indexer"]["summary"]


def test_collect_health_report_includes_deep_baseline_checks(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("agentic_orchestrator.health.evaluate_auto_routing", lambda service: {"summary": {"CORRECT": 30, "ACCEPTABLE": 2, "OVERCALLED": 0, "UNDERCALLED": 0, "WRONG": 0}})
    monkeypatch.setattr("agentic_orchestrator.health.evaluate_task_outputs", lambda service: {"summary": {"COMPLETE": 5, "PARTIAL": 0, "INSUFFICIENT": 0}})
    report = collect_health_report(config, runner=_runner_for_contracts, deep=True)
    checks = {check["name"]: check for check in report["checks"]}
    assert report["deep"] is True
    assert checks["baseline.routing_eval"]["status"] == "OK"
    assert checks["baseline.task_eval"]["status"] == "OK"


def test_render_health_text_includes_summary_and_notes() -> None:
    text = render_health_text(
        {
            "overall_status": "WARNING",
            "generated_at": "2026-04-14T10:00:00+00:00",
            "deep": False,
            "checks": [
                {"name": "tool.agentic_devdocs", "status": "OK", "summary": "ready", "details": {}},
                {"name": "resource.indexer_db", "status": "WARNING", "summary": "stale", "details": {}},
            ],
            "notes": ["example note"],
        }
    )
    assert "Overall: WARNING" in text
    assert "[WARNING] resource.indexer_db: stale" in text
    assert "- example note" in text


def test_collect_health_report_surfaces_mixed_ok_warning_fail_statuses(tmp_path: Path) -> None:
    config = _config(tmp_path)
    old_time = datetime.now(UTC) - timedelta(days=60)
    os.utime(config.devdocs_db_path, (old_time.timestamp(), old_time.timestamp()))

    def mixed_runner(*, args, text, capture_output, check, cwd=None, env=None):
        del text, capture_output, check, cwd, env
        if "runtime-query" in args:
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="boom")
        return _runner_for_contracts(args=args, text=True, capture_output=True, check=False)

    report = collect_health_report(config, runner=mixed_runner)
    checks = {check["name"]: check for check in report["checks"]}
    statuses = {checks["tool.agentic_devdocs"]["status"], checks["resource.devdocs_db"]["status"], checks["contract.agentic_sitemap"]["status"]}
    assert report["overall_status"] == "FAIL"
    assert statuses == {"OK", "WARNING", "FAIL"}
