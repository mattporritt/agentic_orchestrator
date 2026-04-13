# Contributing

## Goal

Keep `agentic_orchestrator` easy to understand, safe to modify, and behaviorally stable.

This repo is a thin orchestration layer, so the best contributions usually:

- clarify docs
- tighten tests
- improve diagnostics
- simplify code structure
- preserve existing contract and evaluation baselines

## Local Setup

1. Create and activate a virtual environment.
2. Install the package in editable mode:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

3. Copy `config.example.toml` to `config.local.toml` and point it at valid local sibling-tool commands and resources.

## Core Commands

Run these before and after changes:

```bash
python3 -m pytest
git status --short
```

Useful live verification command:

```bash
PYTHONPATH=src python3 -m agentic_orchestrator.review_bundle --config ./config.local.toml
```

## Expected Behavior To Preserve

- runtime contract shape
- stable CLI behavior
- routing baseline
- task-eval baseline
- review bundle generation

If a change intentionally affects one of those areas, document it clearly and update the matching tests.

## Coding Guidelines

- prefer explicit logic over clever abstraction
- keep orchestration thin and local
- preserve provenance and grouped tool boundaries
- avoid broad refactors unless they simplify an obvious maintenance problem
- add docstrings/comments only where they clarify intent or invariants

## Tests

Prefer deterministic tests that lock down:

- config precedence and validation
- subprocess command construction
- routing decisions
- grouped merge behavior
- evaluation grading
- review bundle artifacts

Live sibling-tool checks are useful, but unit tests should still pass without the sibling tools installed.
