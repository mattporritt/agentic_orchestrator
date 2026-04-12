# agentic_orchestrator

`agentic_orchestrator` is a thin context-assembly layer over three existing runtime-facing tools:

- `agentic_devdocs`
- `agentic_indexer`
- `agentic_sitemap`

It stays intentionally narrow. It calls those tools in their existing CLI JSON-contract modes, validates the shared outer envelope shape, and merges the resulting docs/code/site context into a single runtime-facing response for a coding agent to consume.

## What It Is

- A minimal orchestrator CLI
- A local subprocess wrapper around the three sibling tools
- A versioned orchestrator runtime contract
- Explicit routing modes: `task`, `auto`, `manual`
- A provenance-preserving context assembler

## What It Is Not

- Not an autonomous agent
- Not a planner/executor
- Not a code editor or code runner
- Not a web service or UI
- Not a database-backed framework
- Not an LLM-calling system

## Runtime Contract

The orchestrator keeps the same outer envelope shape as the sibling tools:

```json
{
  "tool": "agentic_orchestrator",
  "version": "v1",
  "query": "add admin settings to a plugin",
  "normalized_query": "add admin settings to a plugin",
  "intent": {
    "route_mode": "task",
    "task_type": "admin_settings",
    "component_hint": null,
    "source_preferences": ["docs", "code"],
    "tools_considered": ["agentic_devdocs", "agentic_indexer"],
    "routing_notes": ["task_type=admin_settings"],
    "manual_tools": []
  },
  "results": [
    {
      "id": "orchestrated:add-admin-settings-to-a-plugin",
      "type": "orchestrated_context",
      "rank": 1,
      "confidence": "high",
      "source": {
        "name": "orchestrator",
        "type": "multi_tool_runtime",
        "url": null,
        "canonical_url": null,
        "path": null,
        "document_title": null,
        "section_title": null,
        "heading_path": []
      },
      "content": {
        "docs_results": [],
        "code_results": [],
        "site_results": [],
        "suggested_next_steps": [],
        "summary": "Combined context from 2 tool(s)."
      },
      "diagnostics": {
        "tools_called": [],
        "selection_strategy": "rule_based_routing_plus_grouped_merge",
        "notes": []
      }
    }
  ]
}
```

The orchestrator adds a thin merged `content` layer but preserves underlying tool results unchanged inside:

- `docs_results`
- `code_results`
- `site_results`
- `suggested_next_steps`
- `summary`

## Local Tool Configuration

Configuration is explicit and local. You can provide it with a TOML file, CLI flags, and environment variables.

The recommended approach is a config file like [`config.example.toml`](/Users/mattp/projects/agentic_orchestrator/config.example.toml):

```toml
[tools.devdocs]
command = "/Users/you/projects/agentic_devdocs/.venv/bin/python"
workdir = "/Users/you/projects/agentic_devdocs"
extra_args = ["-m", "agentic_docs.cli"]
env = { PYTHONPATH = "/Users/you/projects/agentic_devdocs/src:/Library/.../site-packages" }

[tools.indexer]
command = "/Users/you/projects/agentic_indexer/.venv/bin/moodle-indexer"
workdir = "/Users/you/projects/agentic_indexer"

[tools.sitemap]
command = "/Users/you/projects/agentic_sitemap/.venv/bin/moodle-sitemap"
workdir = "/Users/you/projects/agentic_sitemap"

[resources]
devdocs_db_path = "/Users/you/projects/agentic_devdocs/_smoke_test/agentic-docs.db"
indexer_db_path = "/Users/you/projects/agentic_indexer/.db/moodle-index.sqlite"
sitemap_run_dir = "/Users/you/projects/agentic_sitemap/discovery-runs/2026-04-09T025735Z"
```

Supported per-tool config:

- `command`
- `workdir`
- `extra_args`
- `env`

Supported resource config:

- `devdocs_db_path`
- `indexer_db_path`
- `sitemap_run_dir`

CLI and environment variable overrides are also supported:

- `--config` or `AGENTIC_ORCHESTRATOR_CONFIG`
- `--devdocs-cmd`, `--devdocs-workdir`, `--devdocs-extra-args`
- `--indexer-cmd`, `--indexer-workdir`, `--indexer-extra-args`
- `--sitemap-cmd`, `--sitemap-workdir`, `--sitemap-extra-args`
- `--devdocs-db-path`, `--indexer-db-path`, `--sitemap-run-dir`

Environment variable equivalents:

- `AGENTIC_ORCHESTRATOR_DEVDOCS_COMMAND`
- `AGENTIC_ORCHESTRATOR_DEVDOCS_WORKDIR`
- `AGENTIC_ORCHESTRATOR_DEVDOCS_EXTRA_ARGS`
- `AGENTIC_ORCHESTRATOR_DEVDOCS_ENV_JSON`
- same pattern for `INDEXER` and `SITEMAP`

The orchestrator fails clearly when a configured command is missing, not executable, or missing required resource paths.

## Route Modes

Routing stays explicit and inspectable.

### `task`

This preserves the original narrow task routes for known Moodle development tasks:

- admin settings
- scheduled tasks
- web services
- privacy metadata
- render/UI tasks

### `auto`

This is a broader but still controlled mode. It uses lightweight intent signals to decide whether to call:

- one tool
- two tools
- or all three

Examples:

- docs-oriented queries can call `agentic_devdocs` only
- code-oriented queries can call `agentic_indexer` only
- render/page/workflow queries can call all three
- general questions fall back to `docs + code`

### `manual`

This mode lets the caller force tool selection.

Supported manual selections:

- `docs`
- `code`
- `site`
- any combination of those three

Examples:

```bash
agentic-orchestrator query "privacy providers" --route-mode manual --tools docs
agentic-orchestrator query "render this page" --route-mode manual --tools code,site
agentic-orchestrator query "general Moodle context" --route-mode manual --tools docs --tools code --json
```

## CLI

JSON mode is the main interface:

```bash
agentic-orchestrator query "add admin settings to a plugin" --config ./config.local.toml --json
```

Auto routing:

```bash
agentic-orchestrator query "Where are the docs for privacy providers?" \
  --config ./config.local.toml \
  --route-mode auto \
  --json
```

Manual tool selection:

```bash
agentic-orchestrator query "How should this render in Moodle?" \
  --config ./config.local.toml \
  --route-mode manual \
  --tools code,site \
  --context-json '{"site_lookup":{"mode":"page_type","query":"dashboard"}}' \
  --json
```

## Live Review Bundle

The review bundle now prefers real sibling-tool execution when valid config is present.

Generate a live bundle:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --config ./config.local.toml
```

Only allow deterministic mock fallback when you explicitly want it for testing:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --allow-mock-fallback
```

The review bundle includes:

- `summary.md`
- example orchestrator outputs for representative tasks
- `config-used.json`
- `pytest.txt`
- `git-status.txt`
- `git-commit.txt`
- `routing-report.md`

The summary explicitly states whether each example used `real_local_tools` or `mock_fallback`.

## Representative Flows

- Add admin settings to a plugin
- Register a scheduled task
- Define a web service
- Add privacy metadata
- Understand render/UI context in Moodle

For each, the orchestrator merges the selected tool outputs into one grouped response and emits deterministic suggested next steps grounded in returned evidence.

## Testing

Tests focus on:

- config loading
- missing/misconfigured tool path handling
- adapter command construction
- route-mode selection
- manual tool selection
- merged output shape
- review-bundle real vs fallback selection

They remain deterministic and do not require the sibling tools to be installed for unit-test runs.

## Current Limitations

- Routing is intentionally lightweight and rule-based
- Only a narrow subset of sibling tool commands is wrapped
- Sitemap lookups still rely on explicit or inferable page/page-type/path context
- Live integration depends on explicit local config being correct
- The orchestrator remains a context assembler rather than a planner
