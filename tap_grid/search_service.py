"""Search execution service — the single entry point for running TAP searches.

All search consumers (panels, API endpoints, tests) call execute_search().
No caller invokes execution modes or ORM queries directly.

Read-only enforcement: all queries run through the "search_readonly" DB alias,
which has PostgreSQL default_transaction_read_only=on. Writes are rejected at
the database level (req-grid-search-readonly.sec).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

import jsonschema  # type: ignore[import-untyped]
from django.core.exceptions import ValidationError

from tap_grid.exceptions import SearchExecutionError

if TYPE_CHECKING:
    from tap_grid.models import Search

# DB alias used for all search execution. Configured in settings.py with
# PostgreSQL default_transaction_read_only=on.
_SEARCH_DB_ALIAS = "search_readonly"

# Keys required at the top level of every canonical result envelope.
_ENVELOPE_KEYS = frozenset({"nodes", "edges"})


def execute_search(
    search: "Search",
    inputs: dict[str, Any] | None = None,
    *,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """Execute a Search and return the canonical 4-key graph envelope.

    Args:
        search:  The Search model instance to execute.
        inputs:  Domain-specific execution inputs. Validated against
                 search.input_schema when present.
        limit:   Number of primary-side results to return. Clamped to
                 search.max_limit if set. None means use search.default_limit
                 (which itself may be None, meaning unpaginated).
        offset:  Zero-based offset into the primary-side results. Defaults to 0.

    Returns:
        If paginated: {"count": int, "limit": int, "offset": int, "results": envelope}
        If unpaginated: {"nodes": [...], "edges": [...], "info": {...}, "warnings": {...}}

    Raises:
        ValidationError: inputs fail input_schema validation.
        SearchExecutionError: hard failure during execution.
    """
    validated_inputs = _validate_inputs(search, inputs or {})
    effective_limit, warnings = _resolve_limit(search, limit)
    effective_offset = offset or 0

    start_time = time.monotonic()

    if search.search_type == "module":
        raw_result = _execute_module_search(search, validated_inputs, _SEARCH_DB_ALIAS)
    elif search.search_type == "orm":
        raw_result = _execute_orm_search(
            search,
            validated_inputs,
            _SEARCH_DB_ALIAS,
            effective_limit,
            effective_offset,
        )
    else:
        raise SearchExecutionError(f"Unknown search_type: {search.search_type!r}")

    elapsed_ms = round((time.monotonic() - start_time) * 1000)

    envelope = _normalize_envelope(raw_result)
    envelope["warnings"].update(warnings)
    envelope["info"].update(
        {
            "search_type": search.search_type,
            "root": search.root,
            "elapsed_ms": elapsed_ms,
        }
    )

    if effective_limit is not None:
        count = len(envelope["nodes"]) if search.root == "node" else len(envelope["edges"])
        return {
            "count": count,
            "limit": effective_limit,
            "offset": effective_offset,
            "results": envelope,
        }

    return envelope


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_inputs(search: "Search", inputs: dict[str, Any]) -> dict[str, Any]:
    """Validate execution inputs against search.input_schema.

    Returns the inputs unchanged if validation passes or no schema is set.
    Raises ValidationError on schema violation.
    """
    if not search.input_schema:
        return inputs
    try:
        jsonschema.validate(instance=inputs, schema=search.input_schema)
    except jsonschema.ValidationError as exc:
        raise ValidationError({"inputs": [exc.message]}) from exc
    return inputs


def _resolve_limit(
    search: "Search", caller_limit: int | None
) -> tuple[int | None, dict[str, Any]]:
    """Apply pagination rules and return (effective_limit, warnings).

    1. caller_limit overrides search.default_limit.
    2. Effective limit is clamped to search.max_limit if set.
    3. Clamping is recorded in warnings.
    """
    warnings: dict[str, Any] = {}
    effective = caller_limit if caller_limit is not None else search.default_limit

    if effective is not None and search.max_limit is not None and effective > search.max_limit:
        warnings["max_limit_clamped"] = {
            "requested": effective,
            "clamped_to": search.max_limit,
        }
        effective = search.max_limit

    return effective, warnings


def _normalize_envelope(raw: Any) -> dict[str, Any]:
    """Ensure the raw result is a valid 4-key envelope.

    Raises SearchExecutionError if nodes/edges keys are missing.
    Adds empty info/warnings dicts if absent.
    """
    if not isinstance(raw, dict) or not _ENVELOPE_KEYS.issubset(raw.keys()):
        raise SearchExecutionError(
            f"Search result must be a dict with at least 'nodes' and 'edges' keys. "
            f"Got: {type(raw).__name__} with keys {sorted(raw.keys()) if isinstance(raw, dict) else 'N/A'}"
        )
    return {
        "nodes": raw["nodes"],
        "edges": raw["edges"],
        "info": dict(raw.get("info") or {}),
        "warnings": dict(raw.get("warnings") or {}),
    }


# ---------------------------------------------------------------------------
# Execution mode stubs — filled in by later phases
# ---------------------------------------------------------------------------


def _execute_module_search(
    search: "Search",
    validated_inputs: dict[str, Any],
    db_alias: str,
) -> dict[str, Any]:
    """Resolve and invoke a module search runner.

    Looks up the runner via search_runner_registry. Raises SearchRunnerNotFoundError
    if the key is not registered. Raises SearchExecutionError if the runner raises
    or returns a malformed result.
    """
    from tap_grid.registry import get_search_runner

    runner_key: str = search.definition.get("runner_key", "")
    if not runner_key:
        raise SearchExecutionError("Module search definition is missing 'runner_key'.")

    runner = get_search_runner(runner_key)  # raises SearchRunnerNotFoundError on miss

    try:
        result = runner(search, validated_inputs, db_alias=db_alias)
    except Exception as exc:
        raise SearchExecutionError(
            f"Runner '{runner_key}' raised an exception: {exc}"
        ) from exc

    return cast(dict[str, Any], result)


def _execute_orm_search(
    search: "Search",
    validated_inputs: dict[str, Any],
    db_alias: str,
    limit: int | None,
    offset: int,
) -> dict[str, Any]:
    """Compile and execute an ORM DSL search."""
    from tap_grid.orm_compiler import compile_orm_query

    try:
        return compile_orm_query(search, db_alias, limit=limit, offset=offset)
    except Exception as exc:
        raise SearchExecutionError(f"ORM search execution failed: {exc}") from exc
