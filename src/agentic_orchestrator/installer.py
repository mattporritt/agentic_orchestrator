# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Thin local bootstrap helpers for sibling tool setup."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentic_orchestrator.errors import InstallationError


Runner = Callable[[list[str], str], None]


@dataclass(frozen=True)
class SiblingToolSpec:
    """Describe one sibling repository and the commands needed to bootstrap it."""

    key: str
    runtime_name: str
    repo_dirname: str
    repo_url: str
    command_relpath: str
    install_kind: str

    def install_commands(self, *, install_browser: bool) -> list[list[str]]:
        """Return the repo-local bootstrap commands for this sibling tool."""

        if self.install_kind == "python":
            commands = [
                [sys.executable, "-m", "venv", ".venv"],
                [".venv/bin/pip", "install", "-e", ".[dev]"],
            ]
            if self.key == "sitemap" and install_browser:
                commands.append([".venv/bin/playwright", "install", "chromium"])
            return commands
        if self.install_kind == "composer":
            return [["composer", "install"]]
        raise InstallationError(f"Unsupported install kind for {self.runtime_name}: {self.install_kind}")

    def command_path(self, install_root: Path) -> Path:
        """Return the runtime command path to write into local config."""

        return install_root / self.repo_dirname / self.command_relpath

    def workdir_path(self, install_root: Path) -> Path:
        """Return the working directory path for this sibling repo."""

        return install_root / self.repo_dirname


SIBLING_TOOL_SPECS: tuple[SiblingToolSpec, ...] = (
    SiblingToolSpec(
        key="devdocs",
        runtime_name="agentic_devdocs",
        repo_dirname="agentic_devdocs",
        repo_url="https://github.com/mattporritt/agentic_devdocs",
        command_relpath=".venv/bin/agentic-docs",
        install_kind="python",
    ),
    SiblingToolSpec(
        key="indexer",
        runtime_name="agentic_indexer",
        repo_dirname="agentic_indexer",
        repo_url="https://github.com/mattporritt/agentic_indexer",
        command_relpath=".venv/bin/moodle-indexer",
        install_kind="python",
    ),
    SiblingToolSpec(
        key="sitemap",
        runtime_name="agentic_sitemap",
        repo_dirname="agentic_sitemap",
        repo_url="https://github.com/mattporritt/agentic_sitemap",
        command_relpath=".venv/bin/moodle-sitemap",
        install_kind="python",
    ),
    SiblingToolSpec(
        key="debug",
        runtime_name="agentic_debug",
        repo_dirname="agentic_debug",
        repo_url="https://github.com/mattporritt/agentic_debug",
        command_relpath="bin/moodle-debug",
        install_kind="composer",
    ),
)


def install_sibling_tools(
    *,
    install_root: str,
    write_config: str | None = None,
    install_sitemap_browser: bool = True,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> dict[str, object]:
    """Clone and bootstrap the sibling tools into one local install root."""

    root = Path(install_root).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise InstallationError(f"Install root is not a directory: {root}")
    if not dry_run:
        root.mkdir(parents=True, exist_ok=True)

    runner = runner or _default_runner
    tools: list[dict[str, object]] = []
    for spec in SIBLING_TOOL_SPECS:
        repo_dir = spec.workdir_path(root)
        if repo_dir.exists() and not repo_dir.is_dir():
            raise InstallationError(f"Sibling path is not a directory: {repo_dir}")

        clone_status = "existing" if repo_dir.exists() else "planned"
        clone_command = ["git", "clone", spec.repo_url, str(repo_dir)]
        if not repo_dir.exists():
            if dry_run:
                clone_status = "would_clone"
            else:
                runner(clone_command, str(root))
                clone_status = "cloned"

        install_commands = spec.install_commands(install_browser=install_sitemap_browser)
        executed_commands: list[list[str]] = []
        for command in install_commands:
            executed_commands.append(command)
            if dry_run:
                continue
            runner(command, str(repo_dir))

        tools.append(
            {
                "tool": spec.runtime_name,
                "repo_url": spec.repo_url,
                "repo_dir": str(repo_dir),
                "command_path": str(spec.command_path(root)),
                "clone_status": clone_status,
                "install_commands": executed_commands,
            }
        )

    written_config = None
    if write_config:
        written_config = str(_write_generated_config(root, Path(write_config).expanduser().resolve()))

    return {
        "install_root": str(root),
        "dry_run": dry_run,
        "install_sitemap_browser": install_sitemap_browser,
        "tools": tools,
        "written_config": written_config,
    }


def render_install_report_text(report: dict[str, object]) -> str:
    """Render a concise human-readable sibling install summary."""

    lines = [
        "Sibling Tool Install",
        f"Install root: {report['install_root']}",
        f"Dry run: {'yes' if report['dry_run'] else 'no'}",
        f"Sitemap browser install: {'yes' if report['install_sitemap_browser'] else 'no'}",
        "",
    ]
    for tool in report["tools"]:
        lines.append(f"- {tool['tool']}: {tool['clone_status']}")
        lines.append(f"  repo: {tool['repo_url']}")
        lines.append(f"  dir: {tool['repo_dir']}")
        lines.append(f"  command: {tool['command_path']}")
    if report.get("written_config"):
        lines.extend(["", f"Config written: {report['written_config']}"])
    return "\n".join(lines) + "\n"


def _write_generated_config(install_root: Path, config_path: Path) -> Path:
    """Write a local config scaffold pointing at the installed sibling tools."""

    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by `agentic-orchestrator install-siblings`.",
        "# Fill in the resource paths after generating local docs/index/sitemap artifacts.",
        "",
    ]
    for spec in SIBLING_TOOL_SPECS:
        lines.extend(
            [
                f"[tools.{spec.key}]",
                f'command = "{spec.command_path(install_root)}"',
                f'workdir = "{spec.workdir_path(install_root)}"',
                "",
            ]
        )
    lines.extend(
        [
            "[resources]",
            f'# devdocs_db_path = "{install_root / "agentic_devdocs" / "_smoke_test" / "agentic-docs.db"}"',
            f'# indexer_db_path = "{install_root / "agentic_indexer" / ".db" / "moodle-index.sqlite"}"',
            f'# sitemap_run_dir = "{install_root / "agentic_sitemap" / "discovery-runs" / "LATEST_RUN_DIR"}"',
            "",
        ]
    )
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def _default_runner(command: list[str], workdir: str) -> None:
    """Run one install command or raise a user-facing installation error."""

    completed = subprocess.run(command, cwd=workdir, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown install failure"
        raise InstallationError(f"Install command failed in {workdir}: {' '.join(command)}\n{detail}")
