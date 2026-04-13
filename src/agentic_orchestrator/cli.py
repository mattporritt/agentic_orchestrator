"""Minimal CLI for the thin orchestration prototype."""

from __future__ import annotations

import argparse
import json
import sys

from agentic_orchestrator.config import OrchestratorConfig, parse_context_json, parse_manual_tools
from agentic_orchestrator.errors import OrchestratorError
from agentic_orchestrator.health import collect_health_report, render_health_text
from agentic_orchestrator.orchestrator import OrchestratorService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-orchestrator",
        description="Thin orchestration prototype over the three runtime-facing Moodle helper tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query", help="Route a task query and merge tool runtime contract outputs.")
    query_parser.add_argument("query_text", help="User or developer task query.")
    query_parser.add_argument("--context-json", help="Optional lightweight context as a JSON object.")
    query_parser.add_argument("--route-mode", choices=["task", "auto", "manual"], default="task", help="Routing mode.")
    query_parser.add_argument("--tools", action="append", help="Manual tool selection, comma-separated or repeated, for example docs,code.")
    query_parser.add_argument("--json", action="store_true", help="Emit the orchestrator runtime JSON contract.")
    _add_common_config_args(query_parser)

    health_parser = subparsers.add_parser("health", help="Check local runtime health, recency, and contract sanity.")
    health_parser.add_argument("--json", action="store_true", help="Emit structured JSON health output.")
    health_parser.add_argument("--deep", action="store_true", help="Also run deeper routing/task baseline sanity checks.")
    _add_common_config_args(health_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = OrchestratorConfig.from_args(args)
        if args.command == "query":
            context = parse_context_json(args.context_json)
            manual_tools = parse_manual_tools(args.tools)
            service = OrchestratorService.from_config(config)
            payload = service.query(
                query=args.query_text,
                context=context,
                route_mode=args.route_mode,
                manual_tools=manual_tools,
            )
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
                return 0

            result = payload["results"][0]
            print(result["content"]["summary"])
            print(f"Route mode: {payload['intent']['route_mode']}")
            print(f"Tools called: {', '.join(call['tool'] for call in result['diagnostics']['tools_called'])}")
            for step in result["content"]["suggested_next_steps"][:5]:
                print(f"- [{step['source_tool']}] {step['kind']}: {step['value']}")
            return 0
        if args.command == "health":
            report = collect_health_report(config, deep=args.deep)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
                return 0
            print(render_health_text(report), end="")
            return 0
        parser.error(f"Unsupported command: {args.command}")
    except (OrchestratorError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 2


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared config/resource override flags used by CLI subcommands."""

    parser.add_argument("--config", help="Optional TOML config file for sibling tool paths and resources.")
    parser.add_argument("--devdocs-cmd", help="Override the devdocs command string.")
    parser.add_argument("--devdocs-workdir", help="Override the devdocs working directory.")
    parser.add_argument("--devdocs-extra-args", help="Override devdocs extra args as a shell-like string.")
    parser.add_argument("--indexer-cmd", help="Override the indexer command string.")
    parser.add_argument("--indexer-workdir", help="Override the indexer working directory.")
    parser.add_argument("--indexer-extra-args", help="Override indexer extra args as a shell-like string.")
    parser.add_argument("--sitemap-cmd", help="Override the sitemap command string.")
    parser.add_argument("--sitemap-workdir", help="Override the sitemap working directory.")
    parser.add_argument("--sitemap-extra-args", help="Override sitemap extra args as a shell-like string.")
    parser.add_argument("--devdocs-db-path", help="Path to the devdocs SQLite DB.")
    parser.add_argument("--indexer-db-path", help="Path to the indexer SQLite DB.")
    parser.add_argument("--sitemap-run-dir", help="Path to the saved sitemap run directory.")


if __name__ == "__main__":
    sys.exit(main())
