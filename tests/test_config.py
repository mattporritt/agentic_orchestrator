# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from agentic_orchestrator.config import OrchestratorConfig, ToolCommandConfig, parse_manual_tools
from agentic_orchestrator.errors import ConfigurationError


def test_config_loads_from_toml_file(tmp_path: Path) -> None:
    config_path = tmp_path / "orchestrator.toml"
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    executable = tool_dir / "dummy-tool"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    config_path.write_text(
        f"""
[tools.devdocs]
command = "{executable}"
workdir = "{tmp_path}"
extra_args = ["-m", "agentic_docs.cli"]

[tools.indexer]
command = "{executable}"

[tools.sitemap]
command = "{executable}"

[tools.debug]
command = "{executable}"

[resources]
devdocs_db_path = "{tmp_path / 'docs.db'}"
indexer_db_path = "{tmp_path / 'index.db'}"
sitemap_run_dir = "{tmp_path / 'run'}"
""".strip(),
        encoding="utf-8",
    )

    config = OrchestratorConfig.from_sources(config_path=str(config_path))
    assert config.devdocs.command == [str(executable)]
    assert config.devdocs.extra_args == ["-m", "agentic_docs.cli"]
    assert config.devdocs.workdir == str(tmp_path)
    assert config.devdocs_db_path == str(tmp_path / "docs.db")
    assert config.debug.command == [str(executable)]


def test_tool_validation_fails_clearly_for_missing_command() -> None:
    config = ToolCommandConfig(name="agentic_devdocs", command=["/missing/tool"])
    with pytest.raises(ConfigurationError, match="does not exist"):
        config.validate()


def test_manual_tool_parsing_supports_comma_separated_and_repeated_values() -> None:
    parsed = parse_manual_tools(["docs,code", "site,debug"])
    assert parsed == ["agentic_devdocs", "agentic_indexer", "agentic_sitemap", "agentic_debug"]


def test_args_override_file_values(tmp_path: Path) -> None:
    config_path = tmp_path / "orchestrator.toml"
    config_path.write_text(
        """
[tools.devdocs]
command = "agentic-docs"

[tools.indexer]
command = "moodle-indexer"

[tools.sitemap]
command = "moodle-sitemap"
""".strip(),
        encoding="utf-8",
    )
    args = Namespace(
        config=str(config_path),
        devdocs_cmd="/override/devdocs",
        devdocs_workdir=None,
        devdocs_extra_args=None,
        indexer_cmd=None,
        indexer_workdir=None,
        indexer_extra_args=None,
        sitemap_cmd=None,
        sitemap_workdir=None,
        sitemap_extra_args=None,
        debug_cmd=None,
        debug_workdir=None,
        debug_extra_args=None,
        devdocs_db_path=None,
        indexer_db_path=None,
        sitemap_run_dir=None,
    )
    config = OrchestratorConfig.from_args(args)
    assert config.devdocs.command == ["/override/devdocs"]


def test_validate_required_resources_fails_when_indexer_db_missing(tmp_path: Path) -> None:
    executable = tmp_path / "tool"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    config = OrchestratorConfig.from_args(
        Namespace(
            config=None,
            devdocs_cmd=str(executable),
            devdocs_workdir=None,
            devdocs_extra_args=None,
            indexer_cmd=str(executable),
            indexer_workdir=None,
            indexer_extra_args=None,
            sitemap_cmd=str(executable),
            sitemap_workdir=None,
            sitemap_extra_args=None,
            debug_cmd=None,
            debug_workdir=None,
            debug_extra_args=None,
            devdocs_db_path="/tmp/devdocs.sqlite",
            indexer_db_path=None,
            sitemap_run_dir="/tmp/run",
        )
    )
    with pytest.raises(ConfigurationError, match="configured indexer DB path"):
        config.validate_required_resources(["agentic_indexer"])
