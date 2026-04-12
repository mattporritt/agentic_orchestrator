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
- A lightweight routing evaluation loop for `auto`

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
      "content": {
        "docs_results": [],
        "code_results": [],
        "site_results": [],
        "suggested_next_steps": [],
        "summary": "Combined context from 2 tool(s)."
      },
      "diagnostics": {
        "tools_called": [],
        "route_mode": "task",
        "routing_reasons": [],
        "selected_tools": [],
        "selection_strategy": "rule_based_routing_plus_grouped_merge",
        "notes": []
      }
    }
  ]
}
```

The orchestrator keeps grouped tool results and preserves provenance:

- `docs_results`
- `code_results`
- `site_results`
- `suggested_next_steps`
- `summary`
- `diagnostics.tools_called`

## Local Tool Configuration

Configuration is explicit and local. You can provide it with a TOML file, CLI flags, and environment variables.

The recommended approach is a config file like [`config.example.toml`](/Users/mattp/projects/agentic_orchestrator/config.example.toml).

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

The orchestrator fails clearly when a configured command is missing, not executable, or missing required resource paths.

## Route Modes

Routing stays explicit and inspectable.

### `task`

This preserves the narrow task routes for known Moodle development tasks such as:

- admin settings
- scheduled tasks
- web services
- privacy metadata
- render/UI tasks

### `auto`

`auto` is broader but still controlled. It uses explicit signal families instead of planner logic:

- conceptual cues: `how does`, `how should`, `where do`, `what do I need`
- implementation/location cues: `wire up`, `register`, `defined`, `what file`, `contains`
- docs concept cues: `privacy`, `scheduled task`, `web service`, `behat`, `output`, `renderer`
- site/workflow cues: `page type`, `workflow`, `navigate`, `screen`, `dashboard`

Typical behavior:

- conceptual implementation questions: `docs + code`
- file-location/debugging questions: usually `code`, sometimes `docs + code`
- generic rendering questions: `docs + code`
- page/workflow/site-context questions: `site`
- page-aware rendering questions: `docs + code + site`

The goal is to call the smallest useful subset of tools, not all three by default.

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

## Routing Evaluation

`auto` routing is now evaluated against an explicit fixture in [`evals/routing_eval_v1.json`](/Users/mattp/projects/agentic_orchestrator/evals/routing_eval_v1.json).

Each case records:

- `preferred_tools`
- `acceptable_tool_sets`
- `disallowed_tools`
- `notes`

Routing quality statuses are deterministic:

- `CORRECT`: selected tools exactly matched the preferred set
- `ACCEPTABLE`: selected tools matched an explicitly acceptable set
- `OVERCALLED`: selected tools formed a useful superset but included an unnecessary extra tool
- `UNDERCALLED`: selected tools omitted a tool expected for the case
- `WRONG`: selected tools did not match any useful expected routing pattern

This evaluation is about tool-set choice, not retrieval quality inside each sibling tool.

## CLI

JSON mode is the main interface:

```bash
agentic-orchestrator query "add admin settings to a plugin" --config ./config.local.toml --json
```

Auto routing:

```bash
agentic-orchestrator query "How should I wire up a service and where is it defined?" \
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

## Routing Review Bundle

The review bundle now focuses on routing quality and prefers real sibling-tool execution when valid config is present.

Generate a routing review bundle:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --config ./config.local.toml
```

Only allow deterministic mock fallback when you explicitly want it for testing:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --allow-mock-fallback
```

The routing review bundle includes:

- `summary.md`
- `routing_eval.json`
- `routing_eval.txt`
- `mode_comparison.json`
- `mode_comparison.md`
- example orchestrator outputs
- `config-used.json`
- `pytest.txt`
- `git-status.txt`
- `git-commit.txt`

The summary explicitly states whether the review used `real_local_tools` or `mock_fallback`.

## Current Limitations

- `auto` remains rule-based and will still miss some edge-case phrasing
- Routing evaluation grades tool-set choice only, not per-tool retrieval quality
- Generic low-signal questions still fall back to `docs + code`
- The orchestrator remains a context assembler rather than a planner
