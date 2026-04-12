"""Configuration loading for local tool commands and resource paths."""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _split_command(value: str) -> list[str]:
    return shlex.split(value.strip())


@dataclass(frozen=True)
class ToolCommandConfig:
    name: str
    command: list[str]


@dataclass(frozen=True)
class OrchestratorConfig:
    devdocs: ToolCommandConfig
    indexer: ToolCommandConfig
    sitemap: ToolCommandConfig
    devdocs_db_path: str | None
    indexer_db_path: str | None
    sitemap_run_dir: str | None

    @classmethod
    def from_args(cls, args: Any) -> "OrchestratorConfig":
        return cls(
            devdocs=ToolCommandConfig(
                name="agentic_devdocs",
                command=_split_command(
                    args.devdocs_cmd or os.getenv("AGENTIC_ORCHESTRATOR_DEVDOCS_CMD", "agentic-docs")
                ),
            ),
            indexer=ToolCommandConfig(
                name="agentic_indexer",
                command=_split_command(
                    args.indexer_cmd or os.getenv("AGENTIC_ORCHESTRATOR_INDEXER_CMD", "moodle-indexer")
                ),
            ),
            sitemap=ToolCommandConfig(
                name="agentic_sitemap",
                command=_split_command(
                    args.sitemap_cmd or os.getenv("AGENTIC_ORCHESTRATOR_SITEMAP_CMD", "moodle-sitemap")
                ),
            ),
            devdocs_db_path=args.devdocs_db_path or os.getenv("AGENTIC_ORCHESTRATOR_DEVDOCS_DB"),
            indexer_db_path=args.indexer_db_path or os.getenv("AGENTIC_ORCHESTRATOR_INDEXER_DB"),
            sitemap_run_dir=args.sitemap_run_dir or os.getenv("AGENTIC_ORCHESTRATOR_SITEMAP_RUN_DIR"),
        )


def parse_context_json(raw: str | None) -> dict[str, Any]:
    """Parse optional lightweight context JSON."""

    if not raw:
        return {}
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("--context-json must decode to a JSON object.")
    return loaded


def resolve_repo_root() -> Path:
    """Return the project root for artifact generation."""

    return Path(__file__).resolve().parents[2]
