# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Configuration loading for local tool commands and resource paths."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_orchestrator.errors import ConfigurationError


TOOL_KEY_MAP = {
    "devdocs": "agentic_devdocs",
    "indexer": "agentic_indexer",
    "sitemap": "agentic_sitemap",
    "debug": "agentic_debug",
}


def _split_command(value: str | list[str] | None) -> list[str]:
    """Normalize CLI config values into an argv-style list."""

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return shlex.split(value.strip())


def _string_map(value: Any) -> dict[str, str]:
    """Validate and normalize environment override mappings."""

    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError("tool env configuration must be a mapping of string keys to string values.")
    return {str(key): str(item) for key, item in value.items()}


@dataclass(frozen=True)
class ToolCommandConfig:
    name: str
    command: list[str]
    workdir: str | None = None
    extra_args: list[str] | None = None
    env: dict[str, str] | None = None

    def command_line(self) -> list[str]:
        """Return the configured executable plus any static extra arguments."""

        return [*self.command, *(self.extra_args or [])]

    def merged_env(self) -> dict[str, str] | None:
        """Overlay configured environment overrides onto the current process env."""

        if not self.env:
            return None
        return {**os.environ, **self.env}

    def resolved_program(self) -> str:
        """Resolve the executable path and fail with a user-facing error if missing."""

        if not self.command:
            raise ConfigurationError(f"{self.name} command is not configured.")
        program = self.command[0]
        if os.path.sep in program or program.startswith("."):
            path = Path(program).expanduser()
            if not path.exists():
                raise ConfigurationError(f"{self.name} command does not exist: {program}")
            if not os.access(path, os.X_OK):
                raise ConfigurationError(f"{self.name} command is not executable: {program}")
            return str(path)
        resolved = shutil.which(program)
        if not resolved:
            raise ConfigurationError(f"{self.name} command not found on PATH: {program}")
        return resolved

    def validate(self) -> None:
        """Validate the executable and optional working directory for one tool."""

        self.resolved_program()
        if self.workdir:
            path = Path(self.workdir).expanduser()
            if not path.exists():
                raise ConfigurationError(f"{self.name} workdir does not exist: {self.workdir}")
            if not path.is_dir():
                raise ConfigurationError(f"{self.name} workdir is not a directory: {self.workdir}")


@dataclass(frozen=True)
class OrchestratorConfig:
    devdocs: ToolCommandConfig
    indexer: ToolCommandConfig
    sitemap: ToolCommandConfig
    debug: ToolCommandConfig
    devdocs_db_path: str | None
    indexer_db_path: str | None
    sitemap_run_dir: str | None
    config_path: str | None = None

    @classmethod
    def from_args(cls, args: Any) -> "OrchestratorConfig":
        return cls.from_sources(
            args=args,
            config_path=getattr(args, "config", None) or os.getenv("AGENTIC_ORCHESTRATOR_CONFIG"),
        )

    @classmethod
    def from_sources(cls, *, args: Any | None = None, config_path: str | None = None) -> "OrchestratorConfig":
        raw = load_config_file(config_path)
        args = args or object()
        tools = raw.get("tools", {})
        resources = raw.get("resources", {})

        return cls(
            devdocs=_build_tool_config("devdocs", args=args, file_tools=tools, default_command="agentic-docs"),
            indexer=_build_tool_config("indexer", args=args, file_tools=tools, default_command="moodle-indexer"),
            sitemap=_build_tool_config("sitemap", args=args, file_tools=tools, default_command="moodle-sitemap"),
            debug=_build_tool_config("debug", args=args, file_tools=tools, default_command=None),
            devdocs_db_path=_first_value(
                getattr(args, "devdocs_db_path", None),
                os.getenv("AGENTIC_ORCHESTRATOR_DEVDOCS_DB"),
                resources.get("devdocs_db_path"),
            ),
            indexer_db_path=_first_value(
                getattr(args, "indexer_db_path", None),
                os.getenv("AGENTIC_ORCHESTRATOR_INDEXER_DB"),
                resources.get("indexer_db_path"),
            ),
            sitemap_run_dir=_resolve_sitemap_run_dir(
                _first_value(
                    getattr(args, "sitemap_run_dir", None),
                    os.getenv("AGENTIC_ORCHESTRATOR_SITEMAP_RUN_DIR"),
                    resources.get("sitemap_run_dir"),
                )
            ),
            config_path=config_path,
        )

    def tool_config(self, tool_name: str) -> ToolCommandConfig:
        """Return the concrete tool config for a runtime-facing tool name."""

        if tool_name == "agentic_devdocs":
            return self.devdocs
        if tool_name == "agentic_indexer":
            return self.indexer
        if tool_name == "agentic_sitemap":
            return self.sitemap
        if tool_name == "agentic_debug":
            return self.debug
        raise ConfigurationError(f"Unknown tool config requested: {tool_name}")

    def validate_tool(self, tool_name: str) -> None:
        self.tool_config(tool_name).validate()

    def validate_required_resources(self, tool_names: list[str]) -> None:
        """Check that commands and backing resources exist for the requested tools."""

        for tool_name in tool_names:
            self.validate_tool(tool_name)
            if tool_name == "agentic_devdocs" and not self.devdocs_db_path:
                raise ConfigurationError("Devdocs queries require a configured devdocs DB path.")
            if tool_name == "agentic_indexer" and not self.indexer_db_path:
                raise ConfigurationError("Indexer queries require a configured indexer DB path.")
            if tool_name == "agentic_sitemap" and not self.sitemap_run_dir:
                raise ConfigurationError("Sitemap queries require a configured sitemap run directory.")

    def tool_path_report(self) -> list[dict[str, Any]]:
        """Return a review-friendly summary of configured tool commands."""

        report: list[dict[str, Any]] = []
        for tool_name in ("agentic_devdocs", "agentic_indexer", "agentic_sitemap", "agentic_debug"):
            tool = self.tool_config(tool_name)
            report.append(
                {
                    "tool": tool_name,
                    "program": tool.command[0] if tool.command else None,
                    "workdir": tool.workdir,
                    "extra_args": list(tool.extra_args or []),
                }
            )
        return report


def _resolve_sitemap_run_dir(path: str | None) -> str | None:
    """Resolve sitemap_run_dir to a concrete run directory.

    Accepts either a direct run directory (containing sitemap.json) or a
    parent discovery-runs directory, in which case the latest subdirectory
    that contains a sitemap.json is selected by lexicographic sort (ISO
    timestamp names sort correctly).
    """
    if path is None:
        return None
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return path
    if (resolved / "sitemap.json").exists():
        return str(resolved)
    candidates = sorted(
        (d for d in resolved.iterdir() if d.is_dir()),
        reverse=True,
    )
    for candidate in candidates:
        if (candidate / "sitemap.json").exists():
            return str(candidate)
    return path


def _first_value(*values: Any) -> Any:
    """Return the first non-None value from an ordered precedence chain."""

    for value in values:
        if value is not None:
            return value
    return None


def _build_tool_config(
    key: str,
    *,
    args: Any,
    file_tools: dict[str, Any],
    default_command: str | None,
) -> ToolCommandConfig:
    """Build one tool config from CLI args, environment, and optional TOML values."""

    tool_file = file_tools.get(key, {}) if isinstance(file_tools, dict) else {}
    env_prefix = f"AGENTIC_ORCHESTRATOR_{key.upper()}"
    command = _split_command(
        _first_value(
            getattr(args, f"{key}_cmd", None),
            os.getenv(f"{env_prefix}_COMMAND"),
            tool_file.get("command"),
            default_command,
        )
    )
    workdir = _first_value(
        getattr(args, f"{key}_workdir", None),
        os.getenv(f"{env_prefix}_WORKDIR"),
        tool_file.get("workdir"),
    )
    extra_args = _split_command(
        _first_value(
            getattr(args, f"{key}_extra_args", None),
            os.getenv(f"{env_prefix}_EXTRA_ARGS"),
            tool_file.get("extra_args"),
        )
    )
    env_raw = tool_file.get("env")
    env_override = os.getenv(f"{env_prefix}_ENV_JSON")
    env = _string_map(env_raw)
    if env_override:
        env.update(_string_map(json.loads(env_override)))
    return ToolCommandConfig(
        name=TOOL_KEY_MAP[key],
        command=command,
        workdir=str(workdir) if workdir is not None else None,
        extra_args=extra_args,
        env=env or None,
    )


def load_config_file(path: str | None) -> dict[str, Any]:
    """Load an optional TOML config file."""

    if not path:
        return {}
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise ConfigurationError(f"Config file does not exist: {config_path}")
    with config_path.open("rb") as handle:
        loaded = tomllib.load(handle)
    if not isinstance(loaded, dict):
        raise ConfigurationError("Config file must decode to a TOML table.")
    return loaded


def parse_context_json(raw: str | None) -> dict[str, Any]:
    """Parse optional lightweight context JSON."""

    if not raw:
        return {}
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("--context-json must decode to a JSON object.")
    return loaded


def parse_manual_tools(raw_values: list[str] | None) -> list[str]:
    """Parse repeated or comma-separated manual tool selection values."""

    if not raw_values:
        return []
    alias_map = {
        "docs": "agentic_devdocs",
        "devdocs": "agentic_devdocs",
        "agentic_devdocs": "agentic_devdocs",
        "code": "agentic_indexer",
        "indexer": "agentic_indexer",
        "agentic_indexer": "agentic_indexer",
        "site": "agentic_sitemap",
        "sitemap": "agentic_sitemap",
        "agentic_sitemap": "agentic_sitemap",
        "debug": "agentic_debug",
        "agentic_debug": "agentic_debug",
    }
    parsed: list[str] = []
    for raw in raw_values:
        for part in raw.split(","):
            normalized = part.strip().lower()
            if not normalized:
                continue
            if normalized not in alias_map:
                raise ConfigurationError(f"Unsupported tool selection '{part.strip()}'.")
            mapped = alias_map[normalized]
            if mapped not in parsed:
                parsed.append(mapped)
    return parsed


def resolve_repo_root() -> Path:
    """Return the project root for artifact generation."""

    return Path(__file__).resolve().parents[2]
