from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from agentic_orchestrator.config import OrchestratorConfig
from agentic_orchestrator.review_bundle import build_review_runtime, generate_review_bundle


def _tool_script(path: Path) -> str:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def test_review_bundle_runtime_uses_mock_fallback_when_allowed(tmp_path: Path) -> None:
    runtime = build_review_runtime(config_path=str(tmp_path / "missing.toml"), allow_mock_fallback=True)
    assert runtime.execution_mode == "mock_fallback"


def test_review_bundle_runtime_prefers_real_tools_when_configured(tmp_path: Path) -> None:
    script = _tool_script(tmp_path / "tool")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    config_path = tmp_path / "orchestrator.toml"
    config_path.write_text(
        f"""
[tools.devdocs]
command = "{script}"

[tools.indexer]
command = "{script}"

[tools.sitemap]
command = "{script}"

[resources]
devdocs_db_path = "{tmp_path / 'docs.db'}"
indexer_db_path = "{tmp_path / 'index.db'}"
sitemap_run_dir = "{run_dir}"
""".strip(),
        encoding="utf-8",
    )
    runtime = build_review_runtime(config_path=str(config_path), allow_mock_fallback=False)
    assert runtime.execution_mode == "real_local_tools"


def test_generate_review_bundle_can_use_mock_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agentic_orchestrator.review_bundle.resolve_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "agentic_orchestrator.review_bundle._write_command_output",
        lambda path, command, **kwargs: path.write_text(f"$ {' '.join(command)}\n[exit_code=0]\n", encoding="utf-8"),
    )
    bundle_dir = generate_review_bundle(config_path=str(tmp_path / "missing.toml"), allow_mock_fallback=True)
    summary = (bundle_dir / "summary.md").read_text(encoding="utf-8")
    config_used = json.loads((bundle_dir / "config-used.json").read_text(encoding="utf-8"))
    routing_eval = json.loads((bundle_dir / "routing_eval.json").read_text(encoding="utf-8"))
    assert "mock_fallback" in summary
    assert config_used["tools"][0]["tool"] == "agentic_devdocs"
    assert "summary" in routing_eval
    assert (bundle_dir / "mode_comparison.md").exists()
