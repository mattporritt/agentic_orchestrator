"""Runtime contract helpers for the orchestrator and sibling tool envelopes."""

from __future__ import annotations

from hashlib import sha1
from typing import Any

from agentic_orchestrator.errors import ContractValidationError


ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def normalize_query(value: str | None) -> str:
    """Return a stable normalized query string."""

    return " ".join(str(value or "").strip().lower().split())


def stable_id(*parts: str) -> str:
    """Build a deterministic short identifier."""

    material = "||".join(part.strip() for part in parts)
    return sha1(material.encode("utf-8")).hexdigest()[:16]


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{context} must be a JSON object.")
    return payload


def _require_string(value: Any, field: str, context: str) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{context} field '{field}' must be a string.")
    return value


def _require_list(value: Any, field: str, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{context} field '{field}' must be a list.")
    return value


def validate_runtime_envelope(payload: Any, *, expected_tool: str | None = None) -> dict[str, Any]:
    """Validate the shared runtime-facing outer contract shape."""

    data = _require_mapping(payload, "runtime contract")
    for field in ("tool", "version", "query", "normalized_query", "intent", "results"):
        if field not in data:
            raise ContractValidationError(f"runtime contract missing required field '{field}'.")

    tool = _require_string(data["tool"], "tool", "runtime contract")
    version = _require_string(data["version"], "version", "runtime contract")
    _require_string(data["query"], "query", "runtime contract")
    _require_string(data["normalized_query"], "normalized_query", "runtime contract")
    _require_mapping(data["intent"], "runtime contract intent")
    results = _require_list(data["results"], "results", "runtime contract")

    if expected_tool is not None and tool != expected_tool:
        raise ContractValidationError(f"expected tool '{expected_tool}' but received '{tool}'.")
    if version != "v1":
        raise ContractValidationError(f"unsupported runtime contract version '{version}'.")

    validated_results: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        item = _require_mapping(result, f"runtime result {index}")
        for field in ("id", "type", "rank", "confidence", "source", "content", "diagnostics"):
            if field not in item:
                raise ContractValidationError(f"runtime result {index} missing required field '{field}'.")

        _require_string(item["id"], "id", f"runtime result {index}")
        _require_string(item["type"], "type", f"runtime result {index}")
        if not isinstance(item["rank"], int):
            raise ContractValidationError(f"runtime result {index} field 'rank' must be an integer.")
        confidence = _require_string(item["confidence"], "confidence", f"runtime result {index}")
        if confidence not in ALLOWED_CONFIDENCE:
            raise ContractValidationError(
                f"runtime result {index} field 'confidence' must be one of {sorted(ALLOWED_CONFIDENCE)}."
            )

        source = _require_mapping(item["source"], f"runtime result {index} source")
        for field in (
            "name",
            "type",
            "url",
            "canonical_url",
            "path",
            "document_title",
            "section_title",
            "heading_path",
        ):
            if field not in source:
                raise ContractValidationError(f"runtime result {index} source missing required field '{field}'.")
        _require_string(source["name"], "name", f"runtime result {index} source")
        _require_string(source["type"], "type", f"runtime result {index} source")
        if not isinstance(source["heading_path"], list):
            raise ContractValidationError(f"runtime result {index} source field 'heading_path' must be a list.")
        _require_mapping(item["content"], f"runtime result {index} content")
        _require_mapping(item["diagnostics"], f"runtime result {index} diagnostics")
        validated_results.append(item)

    return {
        "tool": tool,
        "version": version,
        "query": data["query"],
        "normalized_query": data["normalized_query"],
        "intent": data["intent"],
        "results": validated_results,
    }


def orchestrator_source() -> dict[str, Any]:
    """Return the orchestrator provenance shell."""

    return {
        "name": "orchestrator",
        "type": "multi_tool_runtime",
        "url": None,
        "canonical_url": None,
        "path": None,
        "document_title": None,
        "section_title": None,
        "heading_path": [],
    }


def build_orchestrator_envelope(
    *,
    query: str,
    intent: dict[str, Any],
    docs_results: list[dict[str, Any]],
    code_results: list[dict[str, Any]],
    site_results: list[dict[str, Any]],
    debug_results: list[dict[str, Any]],
    key_signals: list[dict[str, Any]],
    tools_called: list[dict[str, Any]],
    suggested_next_steps: list[dict[str, Any]],
    summary: str,
    notes: list[str],
) -> dict[str, Any]:
    """Build the orchestrator runtime-facing envelope."""

    content = {
        "docs_results": docs_results,
        "code_results": code_results,
        "site_results": site_results,
        "debug_results": debug_results,
        "key_signals": key_signals,
        "suggested_next_steps": suggested_next_steps,
        "summary": summary,
    }
    diagnostics = {
        "tools_called": tools_called,
        "selection_strategy": "rule_based_routing_plus_grouped_merge",
        "notes": notes,
    }
    return {
        "tool": "agentic_orchestrator",
        "version": "v1",
        "query": query,
        "normalized_query": normalize_query(query),
        "intent": intent,
        "results": [
            {
                "id": stable_id("orchestrated_context", query),
                "type": "orchestrated_context",
                "rank": 1,
                "confidence": _merge_confidence(docs_results, code_results, site_results, debug_results),
                "source": orchestrator_source(),
                "content": content,
                "diagnostics": diagnostics,
            }
        ],
    }


def _merge_confidence(
    docs_results: list[dict[str, Any]],
    code_results: list[dict[str, Any]],
    site_results: list[dict[str, Any]],
    debug_results: list[dict[str, Any]],
) -> str:
    total = sum(bool(group) for group in (docs_results, code_results, site_results, debug_results))
    if total >= 2:
        return "high"
    if total == 1:
        return "medium"
    return "low"
