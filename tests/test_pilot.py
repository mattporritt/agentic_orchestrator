# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.pilot import collect_pilot_report, create_pilot_trial, render_pilot_report_text, update_pilot_trial


class _FakeService:
    def query(self, *, query: str, context: dict | None = None, route_mode: str = "task", manual_tools: list[str] | None = None) -> dict:
        del context
        selected_tools = list(manual_tools or ["agentic_devdocs", "agentic_indexer"])
        return {
            "tool": "agentic_orchestrator",
            "version": "v1",
            "query": query,
            "normalized_query": query.lower(),
            "intent": {"route_mode": route_mode, "manual_tools": manual_tools or []},
            "results": [
                {
                    "id": "orchestrated:test",
                    "type": "orchestrated_context",
                    "rank": 1,
                    "confidence": "high",
                    "source": {
                        "name": "orchestrator",
                        "type": "multi_tool_runtime",
                        "url": None,
                        "canonical_url": None,
                        "path": None,
                        "document_title": None,
                        "section_title": None,
                        "heading_path": [],
                    },
                    "content": {
                        "docs_results": [],
                        "code_results": [],
                        "site_results": [],
                        "suggested_next_steps": [{"kind": "inspect_file", "value": "settings.php", "source_tool": "agentic_indexer"}],
                        "summary": "Combined context",
                    },
                    "diagnostics": {
                        "tools_called": [{"tool": tool, "mode": "build-context-bundle", "reason": "test", "command": [], "workdir": None} for tool in selected_tools],
                        "route_mode": route_mode,
                        "routing_reasons": [],
                        "selected_tools": selected_tools,
                        "selection_strategy": "test",
                        "notes": [],
                    },
                }
            ],
        }


def _config() -> OrchestratorConfig:
    return OrchestratorConfig.from_args(
        Namespace(
            config=None,
            devdocs_cmd="/bin/sh",
            devdocs_workdir=None,
            devdocs_extra_args=None,
            indexer_cmd="/bin/sh",
            indexer_workdir=None,
            indexer_extra_args=None,
            sitemap_cmd="/bin/sh",
            sitemap_workdir=None,
            sitemap_extra_args=None,
            devdocs_db_path="/tmp/devdocs.sqlite",
            indexer_db_path="/tmp/index.sqlite",
            sitemap_run_dir="/tmp/sitemap-run",
        )
    )


def test_create_pilot_trial_writes_trial_json_and_summary(tmp_path: Path) -> None:
    trial_dir = create_pilot_trial(
        _FakeService(),
        _config(),
        query="add admin settings to a plugin",
        route_mode="task",
        task_label="admin_settings",
        pilot_root=str(tmp_path),
    )
    artifact = json.loads((trial_dir / "trial.json").read_text(encoding="utf-8"))
    summary = (trial_dir / "summary.md").read_text(encoding="utf-8")
    assert artifact["task_label"] == "admin_settings"
    assert artifact["outcome"]["outcome"] == "not_reviewed"
    assert artifact["selected_tools"] == ["agentic_devdocs", "agentic_indexer"]
    assert "Combined context" in summary


def test_update_pilot_trial_overwrites_outcome_fields(tmp_path: Path) -> None:
    trial_dir = create_pilot_trial(
        _FakeService(),
        _config(),
        query="define a web service",
        route_mode="manual",
        manual_tools=["agentic_indexer"],
        pilot_root=str(tmp_path),
    )
    update_pilot_trial(
        trial_dir.name,
        pilot_root=str(tmp_path),
        outcome="useful",
        notes="helped narrow the right files",
        files_touched=["db/services.php"],
        did_it_help_find_right_files=True,
        did_it_help_find_right_docs=False,
    )
    artifact = json.loads((trial_dir / "trial.json").read_text(encoding="utf-8"))
    assert artifact["outcome"]["outcome"] == "useful"
    assert artifact["outcome"]["files_touched"] == ["db/services.php"]
    assert artifact["outcome"]["did_it_help_find_right_files"] is True
    assert artifact["outcome"]["did_it_help_find_right_docs"] is False


def test_update_pilot_trial_preserves_existing_outcome_when_not_reprovided(tmp_path: Path) -> None:
    trial_dir = create_pilot_trial(
        _FakeService(),
        _config(),
        query="privacy metadata",
        route_mode="task",
        pilot_root=str(tmp_path),
        outcome="useful",
    )
    update_pilot_trial(trial_dir.name, pilot_root=str(tmp_path), notes="still useful")
    artifact = json.loads((trial_dir / "trial.json").read_text(encoding="utf-8"))
    assert artifact["outcome"]["outcome"] == "useful"
    assert artifact["outcome"]["notes"] == "still useful"


def test_collect_pilot_report_summarizes_trials(tmp_path: Path) -> None:
    create_pilot_trial(
        _FakeService(),
        _config(),
        query="privacy metadata",
        route_mode="task",
        task_label="privacy",
        pilot_root=str(tmp_path),
        outcome="useful",
    )
    create_pilot_trial(
        _FakeService(),
        _config(),
        query="render task",
        route_mode="auto",
        task_label="render",
        pilot_root=str(tmp_path),
        outcome="partially_useful",
        manual_tools=["agentic_indexer"],
    )
    report = collect_pilot_report(pilot_root=str(tmp_path))
    text = render_pilot_report_text(report)
    assert report["total_runs"] == 2
    assert report["by_outcome"]["useful"] == 1
    assert report["by_route_mode"]["task"] == 1
    assert "Pilot Report" in text
    assert "partially_useful" in text
