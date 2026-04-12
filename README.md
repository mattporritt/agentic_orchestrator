# agentic_orchestrator

`agentic_orchestrator` is a thin context-assembly layer over three existing runtime-facing tools:

- `agentic_devdocs`
- `agentic_indexer`
- `agentic_sitemap`

It is intentionally narrow. It calls those tools in their existing CLI JSON-contract modes, validates the shared outer envelope shape, and merges the resulting docs/code/site context into a single runtime-facing response for a coding agent to consume.

## What It Is

- A minimal orchestrator CLI
- A local subprocess wrapper around the three tools
- A versioned orchestrator runtime contract
- A deterministic rule-based router
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
    "task_type": "admin_settings",
    "component_hint": null,
    "source_preferences": [],
    "tools_considered": ["agentic_devdocs", "agentic_indexer"],
    "routing_notes": ["admin settings keywords matched"]
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

## Routing Strategy

Routing is explicit and inspectable.

- Docs-heavy, conceptual, policy, or subsystem questions call `agentic_devdocs`
- Code structure, symbol, file, or implementation-shape questions call `agentic_indexer`
- UI/page/workflow/site-context questions call `agentic_sitemap`
- Representative Moodle development flows usually call docs + code, with site added for render/UI-style tasks

Supported first-pass flow detection:

- admin settings
- scheduled tasks
- web services
- privacy metadata
- render/UI/Moodle page context

This is not a planner. It is only a small rule set that decides which tools to invoke and records why.

## Configuration

Configuration is deliberately simple.

You can pass values on the CLI or set environment variables.

Tool commands:

- `--devdocs-cmd` or `AGENTIC_ORCHESTRATOR_DEVDOCS_CMD`
- `--indexer-cmd` or `AGENTIC_ORCHESTRATOR_INDEXER_CMD`
- `--sitemap-cmd` or `AGENTIC_ORCHESTRATOR_SITEMAP_CMD`

Resource paths:

- `--devdocs-db-path` or `AGENTIC_ORCHESTRATOR_DEVDOCS_DB`
- `--indexer-db-path` or `AGENTIC_ORCHESTRATOR_INDEXER_DB`
- `--sitemap-run-dir` or `AGENTIC_ORCHESTRATOR_SITEMAP_RUN_DIR`

The command values are shell-like command strings and are split with `shlex`.

Example:

```bash
export AGENTIC_ORCHESTRATOR_DEVDOCS_CMD="python3 /path/to/agentic_devdocs/src/agentic_docs/cli.py"
export AGENTIC_ORCHESTRATOR_INDEXER_CMD="python3 /path/to/agentic_indexer/src/moodle_indexer/cli.py"
export AGENTIC_ORCHESTRATOR_SITEMAP_CMD="python3 /path/to/agentic_sitemap/src/moodle_sitemap/cli.py"
export AGENTIC_ORCHESTRATOR_DEVDOCS_DB="/path/to/devdocs.sqlite"
export AGENTIC_ORCHESTRATOR_INDEXER_DB="/path/to/index.sqlite"
export AGENTIC_ORCHESTRATOR_SITEMAP_RUN_DIR="/path/to/saved-sitemap-run"
```

An example config file is included at [`config.example.toml`](/Users/mattp/projects/agentic_orchestrator/config.example.toml).

## CLI

JSON mode is the main interface:

```bash
agentic-orchestrator query "add admin settings to a plugin" --json
```

Optional lightweight context can be passed as JSON:

```bash
agentic-orchestrator query "How should this render in Moodle?" \
  --context-json '{"site_lookup":{"mode":"page_type","query":"dashboard"}}' \
  --json
```

You can also generate the review artifact bundle:

```bash
python3 -m agentic_orchestrator.review_bundle
```

## Representative Flows

- Add admin settings to a plugin
- Register a scheduled task
- Define a web service
- Add privacy metadata
- Understand render/UI context in Moodle

For each, the orchestrator merges the selected tool outputs into one grouped response and emits deterministic suggested next steps grounded in those results.

## Testing

Tests focus on:

- adapter parsing and validation
- malformed tool contract failures
- routing decisions
- merged output shape
- representative task flows
- provenance/tool separation
- deterministic output structure

They use mocked subprocess responses rather than requiring full live tool installs.

## Current Limitations

- Routing is intentionally small and keyword-based
- Only a narrow subset of tool commands is wrapped
- Sitemap lookups rely on explicit or inferable page/page-type/path context
- The review bundle uses deterministic mock tool responders because the sibling tool dependencies are not installed in this workspace by default

That limitation is deliberate for this first pass: the prototype proves orchestration behavior and contract handling without turning into a larger runtime system.
