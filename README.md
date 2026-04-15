# agentic_orchestrator

`agentic_orchestrator` is a thin context-assembly layer over four existing runtime-facing tools:

- `agentic_devdocs`
- `agentic_indexer`
- `agentic_sitemap`
- `agentic_debug`

It stays intentionally narrow. It calls those tools in their existing CLI JSON-contract modes, validates the shared outer envelope shape, and merges the resulting docs/code/site context into a single runtime-facing response for a coding agent to consume.

## When To Use It

Use the orchestrator when a human developer or coding agent needs a compact, provenance-preserving bundle of Moodle context across:

- documentation and policy guidance from `agentic_devdocs`
- code structure and implementation context from `agentic_indexer`
- page/workflow/site context from `agentic_sitemap`
- explicit bounded debug planning/interpretation/execution context from `agentic_debug`

It is most useful when one task spans more than one of those sources and you want one stable JSON response instead of manually calling each tool.

Do not use it when you need:

- file edits or code execution
- autonomous planning
- a long-running workflow engine
- a replacement for the sibling tools themselves

## Relationship To The Sibling Tools

- `agentic_devdocs`: finds Moodle docs sections, docs-derived file anchors, and conceptual guidance
- `agentic_indexer`: finds files, symbols, context bundles, and implementation companions in the local code index
- `agentic_sitemap`: finds Moodle page types, workflow edges, and site context from a local sitemap run
- `agentic_debug`: handles bounded debugger runtime plans, session interpretation/retrieval, explicit execution, and debugger health checks
- `agentic_orchestrator`: decides which of those tools to call, validates their runtime envelopes, and assembles the grouped result into one response

## Quickstart

### Human Quickstart

1. Create a local virtual environment and install the package:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

2. Make sure the sibling tools are available locally and already have their required resources:

- `agentic_devdocs` with a populated docs DB
- `agentic_indexer` with a populated Moodle index DB
- `agentic_sitemap` with a saved crawl/discovery run
- `agentic_debug` with a working local runtime CLI when you want debug-task integration

3. Copy the example config and point it at your local sibling-tool commands and resources:

```bash
cp config.example.toml config.local.toml
```

4. Run a first query:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli query \
  "add admin settings to a plugin" \
  --config ./config.local.toml \
  --json
```

5. Run the test suite before changing behavior:

```bash
python3 -m pytest
```

6. Run a runtime health check before real orchestrated development work:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli health \
  --config ./config.local.toml
```

7. Generate a live review bundle when you need a verification artifact:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --config ./config.local.toml
```

### AI Worker Quickstart

For a Codex-style worker or other AI assistant:

1. Read this README first for scope and boundaries.
2. Read [`AGENTS.md`](/Users/mattp/projects/agentic_orchestrator/AGENTS.md) for repo-specific commands and safety expectations.
3. Use `config.local.toml` or `_smoke_test/live_config.toml` only if the local environment already has valid sibling-tool resources.
4. Prefer deterministic tests (`python3 -m pytest`) before any live bundle run.
5. Use `health` as a preflight before relying on live sibling-tool results.
6. Keep changes thin: routing, assembly, evaluation, docs, or review-bundle behavior only when clearly within scope.

## What It Is

- A minimal orchestrator CLI
- A local subprocess wrapper around the sibling tools
- A versioned orchestrator runtime contract
- Explicit routing modes: `task`, `auto`, `manual`
- A provenance-preserving context assembler
- A lightweight routing evaluation loop for `auto`
- A conservative bounded debugger integration for explicit debug task families

## What It Is Not

- Not an autonomous agent
- Not a planner/executor
- Not a code editor or code runner
- Not a web service or UI
- Not a database-backed framework
- Not an LLM-calling system
- Not a vague auto-debugger for general bug reports

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
        "debug_results": [],
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
- `debug_results`
- `suggested_next_steps`
- `summary`
- `diagnostics.tools_called`

## Local Tool Configuration

### Prerequisites

You need all of the following available locally before a live run will work:

- Python 3.11+ with `venv`
- this repo installed in a local virtual environment
- a working local checkout of each sibling tool
- a populated `agentic_devdocs` DB
- a populated `agentic_indexer` DB
- a saved `agentic_sitemap` run directory

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
- `--debug-cmd`, `--debug-workdir`, `--debug-extra-args`
- `--devdocs-db-path`, `--indexer-db-path`, `--sitemap-run-dir`

The orchestrator fails clearly when a configured command is missing, not executable, or missing required resource paths.

Typical local setup steps:

1. point each `[tools.*]` section at the sibling tool executable
2. set `workdir` if the tool expects repo-relative behavior
3. add `extra_args` only when needed, for example `["-m", "agentic_docs.cli"]`
4. set the `resources` paths to the real docs DB, index DB, and sitemap run
5. run a JSON query and then the test suite

## Runtime Health / Drift Command

Use the health command as a conservative preflight check before real orchestrated work:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli health --config ./config.local.toml
PYTHONPATH=src python3 -m agentic_orchestrator.cli health --config ./config.local.toml --json
PYTHONPATH=src python3 -m agentic_orchestrator.cli health --config ./config.local.toml --deep
```

What it checks:

- sibling tool command path exists and is executable
- configured tool workdir exists when set
- configured resource paths exist:
  - devdocs DB
  - indexer DB
  - sitemap run directory
- conservative recency/drift checks using resource mtimes
- lightweight runtime-contract sanity calls against each sibling tool
- optional deep baseline checks for routing and task-eval summaries

Health statuses:

- `OK`: the check passed and looks trustworthy
- `WARNING`: the environment is usable but may be stale or drifting
- `FAIL`: the local runtime is not trustworthy enough for normal orchestrated use

What it does not check:

- retrieval quality inside each sibling tool
- every possible runtime command surface
- historical drift over time
- full eval reruns unless `--deep` is requested

Practical examples:

- `OK`: all tool paths resolve, configured resources exist, and each sibling tool returns a valid runtime envelope for its sanity call
- `WARNING`: a resource such as the index DB or sitemap run still exists but is older than the conservative freshness threshold
- `FAIL`: a tool path is missing, a required resource path is absent, or a sibling tool returns malformed/non-zero contract output

## Pilot Trials

Use the pilot harness to record supervised real development-task runs in a lightweight file-based format.

Run a pilot trial:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli pilot-run \
  "add admin settings to a plugin" \
  --config ./config.local.toml \
  --task-label admin_settings \
  --notes "first supervised plugin settings trial"
```

Add or update the human review outcome later:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli pilot-review \
  20260414_101500_add-admin-settings-to-a-plugin \
  --outcome useful \
  --review-notes "helped find settings.php quickly" \
  --helped-find-right-files yes \
  --helped-find-right-docs yes
```

Summarize recorded pilot trials:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli pilot-report
```

Pilot artifacts are lightweight and file-based under `/_smoke_test/pilot_runs` by default. Each trial directory contains:

- `trial.json`: full structured record including the orchestrator output
- `summary.md`: compact human-readable trial summary

Outcome values stay intentionally small:

- `useful`
- `partially_useful`
- `misleading`
- `not_reviewed`

The pilot harness is for supervised usage tracking, not experiment-platform infrastructure. It helps record what was run, what context was returned, and whether a human reviewer found it helpful.

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
- `debug`
- any combination of those three

Examples:

```bash
agentic-orchestrator query "privacy providers" --route-mode manual --tools docs
agentic-orchestrator query "render this page" --route-mode manual --tools code,site
agentic-orchestrator query "general Moodle context" --route-mode manual --tools docs --tools code --json
```

## Debugger Support

`agentic_debug` is integrated conservatively. The orchestrator only routes to it for explicit bounded debug families:

- interpret a stored debug session
- get a stored debug session
- plan debug for a PHPUnit selector
- plan debug for an allowlisted CLI script
- execute bounded debug for a PHPUnit selector
- execute bounded debug for an allowlisted CLI script

Safety boundary:

- safe/proactive: `interpret_session`, `get_session`, `plan_phpunit`, `plan_cli`
- explicit opt-in execution: `execute_phpunit`, `execute_cli`

The orchestrator does not upgrade planning requests into execution, and it does not auto-route vague prompts like `debug this issue` into `agentic_debug`.

Typical examples:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli query \
  "interpret this debug session mds_example_session_id" \
  --config ./config.local.toml \
  --route-mode task \
  --json

PYTHONPATH=src python3 -m agentic_orchestrator.cli query \
  "plan debug for this PHPUnit selector mod_assign\\tests\\grading_test::test_grade_submission" \
  --config ./config.local.toml \
  --route-mode task \
  --json

PYTHONPATH=src python3 -m agentic_orchestrator.cli query \
  "execute cli debug for admin/cli/some_script.php" \
  --config ./config.local.toml \
  --route-mode task \
  --json
```

Debugger evidence is grouped under `debug_results` so the underlying runtime payload stays visible and traceable.

## Routing Evaluation

`auto` routing is evaluated against an explicit fixture in [`evals/routing_eval_v1.json`](/Users/mattp/projects/agentic_orchestrator/evals/routing_eval_v1.json).

Each case records:

- `query_style`
- `preferred_tools`
- `acceptable_tool_sets`
- `disallowed_tools`
- `notes`

The broadened slice now includes harder, more natural Moodle-development wording:

- debugging phrasing such as “not showing up” or “still does not see it”
- messy workflow questions such as “where would I look to understand this page flow?”
- mixed docs+code questions like “where is this service actually wired up?”
- intentionally ambiguous asks where more than one tool set can still be useful

Recent `auto` refinements stayed narrow and explicit:

- `navigation` / `path` / `page flow` wording now counts as workflow or site-context evidence
- subsystem wiring phrases for `service`, `task`, `privacy`, and `settings` can promote `docs + code`
- admin/settings page-flow and Behat page-discovery questions can promote `docs + site`

Routing quality statuses are deterministic:

- `CORRECT`: selected tools exactly matched the preferred set
- `ACCEPTABLE`: selected tools matched an explicitly acceptable set
- `OVERCALLED`: selected tools formed a useful superset but included an unnecessary extra tool
- `UNDERCALLED`: selected tools omitted a tool expected for the case
- `WRONG`: selected tools did not match any useful expected routing pattern

This evaluation is about tool-set choice, not retrieval quality inside each sibling tool.

`query_style` is a small reporting aid, not a planner taxonomy. It helps show which styles are strongest or weakest as the benchmark gets harder:

- `conceptual`
- `implementation`
- `file_location`
- `debugging`
- `ui`
- `workflow`
- `ambiguous`

As the routing eval broadens, lower scores do not automatically mean the router regressed. They can also mean the benchmark is now covering more realistic and less neatly classifiable queries.

## Task Evaluation

Merged task-context usefulness is evaluated against an explicit fixture in [`evals/task_eval_v1.json`](/Users/mattp/projects/agentic_orchestrator/evals/task_eval_v1.json).

The current slice covers a small set of real Moodle development tasks:

- add admin settings to a plugin
- register a scheduled task
- define a web service
- add privacy metadata
- understand how something should render in Moodle

Each case records:

- `expected_tools`
- `required_signals`
- `notes`

Task usefulness statuses are deterministic:

- `COMPLETE`: merged context included the expected tool contributions and required task signals
- `PARTIAL`: merged context was usable but still thin, noisy, or missing one key signal
- `INSUFFICIENT`: merged context was missing expected tools or too many required task signals

The task eval checks for concrete signals such as:

- docs paths and sections
- file anchors and code paths
- symbols or implementation companions when present
- site page type context for render/page tasks
- deterministic, evidence-based `suggested_next_steps`

Recent context-assembly improvements stayed small and explicit:

- promoted compact `key_signals` alongside the grouped tool outputs
- extracted actionable code paths from nested indexer bundles instead of only top-level fields
- filtered noisy external or relative-path anchors from promoted evidence and next steps
- only require per-tool next steps when a tool result actually contains promotable evidence to turn into one
- shape vague render/output code lookups into a narrow indexer-friendly concept query when docs evidence exposes output/template concepts
- route concrete render/output symbol and file queries directly to `agentic_indexer` as bounded code anchors

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

Safe local verification loop:

```bash
python3 -m pytest
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --config ./config.local.toml
```

## Review Bundle

The review bundle now focuses on task-level context usefulness while still reporting routing stability. It prefers real sibling-tool execution when valid config is present.

Generate a live review bundle:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --config ./config.local.toml
```

Only allow deterministic mock fallback when you explicitly want it for testing:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --allow-mock-fallback
```

The review bundle includes:

- `summary.md`
- `task_eval.json`
- `task_eval.txt`
- `routing_eval.json`
- `routing_eval.txt`
- `mode_comparison.json`
- `mode_comparison.md`
- `health.json`
- `health.txt`
- `health_warning.json`
- `health_failure.json`
- `pilot_report.json`
- `pilot_report.txt`
- example orchestrator outputs for the selected task cases
- example pilot trial artifacts under `pilot_trials/`
- `config_used.json`
- `pytest.txt`
- `git_status.txt`
- `git_commit.txt`

The summary explicitly states whether the review used `real_local_tools` or `mock_fallback`.
It also reports whether each task context was `COMPLETE`, `PARTIAL`, or `INSUFFICIENT`, together with missing-signal and noise diagnostics.
Generated artifact names now consistently prefer underscore-separated filenames such as `git_status.txt` and `config_used.json`.

## Current Limitations

- `auto` remains rule-based and will still miss some edge-case phrasing
- Task evaluation grades deterministic signal coverage, not semantic answer quality
- A broader routing eval can expose honest ambiguity or weakness without implying the sibling tools themselves failed
- Generic low-signal questions still fall back to `docs + code`
- The orchestrator remains a context assembler rather than a planner
- Live review runs depend on locally valid sibling-tool resources; the unit tests stay deterministic by mocking subprocess output where appropriate
