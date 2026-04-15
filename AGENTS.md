# AGENTS.md

## Purpose

`agentic_orchestrator` is a thin Moodle context assembler. It calls:

- `agentic_devdocs`
- `agentic_indexer`
- `agentic_sitemap`
- `agentic_debug`

and merges their runtime-contract outputs into one grouped response for a coding agent or human reviewer.

It is not a planner, not an autonomous agent, and not a workflow engine.

## Boundaries

Keep changes within one of these areas unless the user explicitly broadens scope:

- routing
- orchestration and grouped merge behavior
- config loading
- evaluation fixtures and grading
- review bundle generation
- docs and test hardening

Do not add:

- LLM calls
- network services
- autonomous planning
- code editing or execution features
- sibling-tool contract redesigns

## First Commands

Use these first when entering the repo:

```bash
python3 -m pytest
git status --short
```

For live local verification:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.cli health --config ./config.local.toml
PYTHONPATH=src python3 -m agentic_orchestrator.cli pilot-run "add admin settings to a plugin" --config ./config.local.toml --task-label admin_settings
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --config ./config.local.toml
```

## Architecture Map

- `src/agentic_orchestrator/config.py`: explicit config loading and resource validation
- `src/agentic_orchestrator/adapters.py`: subprocess wrappers for sibling tools
- `src/agentic_orchestrator/routing.py`: `task`, `auto`, and `manual` routing
- `src/agentic_orchestrator/orchestrator.py`: request shaping, tool execution, grouped merge, promoted evidence
- `src/agentic_orchestrator/routing_eval.py`: routing evaluation
- `src/agentic_orchestrator/task_eval.py`: task-level usefulness evaluation
- `src/agentic_orchestrator/review_bundle.py`: live/mock artifact generation
- `src/agentic_orchestrator/review_reporting.py`: summary/serialization helpers for bundle output
- `src/agentic_orchestrator/health.py`: local runtime health, recency, and drift checks
- `src/agentic_orchestrator/pilot.py`: lightweight supervised pilot trial recording and reporting
- `src/agentic_orchestrator/debug_eval.py`: conservative debugger-route evaluation slice

## Safe Change Pattern

1. Read the affected module and nearby tests.
2. Prefer explicit small helpers over clever abstraction.
3. Preserve:
   - runtime contract shape
   - routing baseline
   - task-eval baseline
   - CLI behavior
4. Add or update deterministic tests.
5. Re-run `python3 -m pytest`.
6. Only run live sibling-tool checks when the local config and resources are already valid.

## Smoke / Review Artifacts

Place generated smoke-test or review files under `/_smoke_test` in the repo root.
