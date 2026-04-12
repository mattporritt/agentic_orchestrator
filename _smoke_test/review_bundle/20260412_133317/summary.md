# Review Summary

## What The Orchestrator Does

- Accepts a task query and optional lightweight context
- Applies explicit rule-based routing to the three runtime-facing tools
- Calls each selected tool via subprocess JSON-contract mode
- Validates the shared outer envelope shape
- Merges tool results into grouped docs/code/site sections
- Emits deterministic suggested next steps grounded in returned evidence

## Example Tool Routing

- Admin settings: devdocs + indexer
- Scheduled task: devdocs + indexer
- Web service: devdocs + indexer
- Privacy metadata: devdocs + indexer
- Render/UI: devdocs + indexer + sitemap

## Merged Result Structure

- `docs_results` preserve original devdocs contract results
- `code_results` preserve original indexer contract results
- `site_results` preserve original sitemap contract results
- `suggested_next_steps` are derived deterministically from returned provenance
- `diagnostics.tools_called` records which tools ran and why

## Intentionally Out Of Scope

- Autonomous planning
- Code modification or execution
- LLM calls
- APIs, services, or persistent orchestration state

## Notes

- Example outputs in this bundle are generated with deterministic mock tool responders because the sibling tool dependencies are not installed in this workspace by default.
- Unit tests still exercise the subprocess adapter and contract-validation boundaries directly.

Review artifact bundle path: /Users/mattp/projects/agentic_orchestrator/_smoke_test/review_bundle/20260412_133317
