"""CollectorBase — abstract base class for tap_cares collector implementations.

req-tap-cares-collector-module-class, req-tap-cares-collector-job-sole-writer,
req-tap-cares-collector-failure-mode (spec-tap-cares-collector.md).

Concrete collector classes register with `collector_registry` via
`tap_cares.registry.register_collector`. The runtime resolves the registered
class, builds a CollectorConfig, instantiates with that config, and calls
run().

#### The accumulator pattern

Collector instances carry three accumulator attributes — `self.results`,
`self.grift_batches`, `self.summary` — that the collector mutates
during `run()` via helper methods (`record_info` / `record_warn` /
`record_error` / `submit_grift`). The accumulators live entirely in memory
during the run. The `run_collector` task body persists the accumulated state
to `CollectionJob` in a single terminal patch (status + finished_at +
summary + results + grift_batches) after `run()` returns or raises.

This is the structural fix for the v0-pre-refactor multi-writer / staleness
pattern. The task body is the sole writer to CollectionJob; collector code
never sees a CollectionJob handle and cannot write to the database except
through `self.submit_grift(...)` (which writes Batch + node + edge rows
through `grift_import`, never the CollectionJob row).

#### The summary field

`self.summary` is the at-a-glance one-line description of what happened on
this run — success or failure. Collectors set it when they have something
to say (e.g. "Imported 46 indicators (rev_pin v0.1.4)" on success;
"Upstream returned malformed JSON" on failure). The task body writes
`self.summary` verbatim to `CollectionJob.summary` at terminal state.

When a collector fails without setting `self.summary`, the task body
derives a count-based fallback from `self.results["error"]`
("Failed with N error(s)"), and ultimately falls back to the exception's
class and message. See `req-tap-cares-collector-failure-mode`.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import jsonschema

from tap_cares.collectors.config import CollectorConfig

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "collection_job_results.schema.json"
_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())
_ENTRY_SCHEMA: dict[str, Any] = _SCHEMA["$defs"]["entry"]

_LEVELS = ("info", "warn", "error")


def _validate_entry(entry: dict[str, Any]) -> None:
    """Validate one structured-result entry against the pinned per-entry schema.

    Raises jsonschema.ValidationError on any structural violation. Callers
    should let it propagate — bad entries are programming errors, not runtime
    conditions to swallow.
    """
    jsonschema.validate(instance=entry, schema=_ENTRY_SCHEMA)


class CollectorBase(ABC):
    """Abstract base for tap_cares collector implementations.

    Subclasses implement `run()`. They use `self.record_info` / `record_warn` /
    `record_error` to accumulate structured events and `self.submit_grift` to
    push collected data through the GRIFT import surface. The task runtime
    reads `self.results`, `self.grift_batches`, and `self.summary` after
    `run()` returns or raises and writes them to `CollectionJob` in a single
    terminal patch.
    """

    def __init__(self, config: CollectorConfig) -> None:
        self.config = config
        # In-memory accumulators. Populated by record_*/submit_grift during run().
        # The run_collector task body persists them to CollectionJob at terminal state.
        self.results: dict[str, list[dict[str, Any]]] = {"info": [], "warn": [], "error": []}
        self.grift_batches: dict[str, list[str]] = {"imported": [], "skipped": []}
        # At-a-glance one-line description of what happened on this run.
        # Collectors set this freely on either success or failure. On failure
        # without a collector-set summary, the task body derives a count-based
        # fallback ("Failed with N error(s)").
        self.summary: str = ""

    @abstractmethod
    def run(self) -> None:
        """Execute one collection.

        v0 receives no direct arguments — per-run data flows through self.config.
        Implementations may submit results through `self.submit_grift` (the
        approved GRIFT import surface) but must not mutate grid state through
        other paths.
        """
        ...

    # ------------------------------------------------------------------
    # Result accumulators — mutate self.results in memory; the task body
    # persists everything at terminal state.
    # ------------------------------------------------------------------

    def record_info(
        self,
        site: str,
        code: str,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record an info-level event into `self.results["info"]`.

        Args:
            site: UUIDv7 hardcoded at the callsite (generated via scripts/uuid7).
                Required positional — forgetting it raises TypeError. Survives
                refactors; grep the codebase for the UUID to locate the callsite.
            code: Machine-readable category in UPPER_SNAKE.
            message: Human-readable prose specific to this occurrence.
            context: Free-form structured payload. Defaults to {}.
        """
        self._record("info", site, code, message, context)

    def record_warn(
        self,
        site: str,
        code: str,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a warn-level event. Same shape as `record_info`; goes to the warn bucket."""
        self._record("warn", site, code, message, context)

    def record_error(
        self,
        site: str,
        code: str,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record an error-level event. Same shape as `record_info`; goes to the error bucket.

        Pure accumulator — does NOT raise on its own. To abort a run, the
        collector raises an exception after calling `record_error` (per
        `req-tap-cares-collector-failure-mode-4`).
        """
        self._record("error", site, code, message, context)

    def _record(
        self,
        level: str,
        site: str,
        code: str,
        message: str,
        context: dict[str, Any] | None,
    ) -> None:
        if level not in _LEVELS:
            raise ValueError(f"Invalid level {level!r}; expected one of {_LEVELS}.")

        entry: dict[str, Any] = {
            "site": site,
            "code": code,
            "message": message,
            "context": context if context is not None else {},
        }
        _validate_entry(entry)

        # Defensive init in case a subclass touched self.results manually.
        if not isinstance(self.results, dict):
            self.results = {"info": [], "warn": [], "error": []}
        for lvl in _LEVELS:
            self.results.setdefault(lvl, [])

        self.results[level].append(entry)

    # ------------------------------------------------------------------
    # GRIFT submission — imports through the standard importer and
    # accumulates resulting batch IDs on self.grift_batches.
    # ------------------------------------------------------------------

    def submit_grift(
        self,
        document: dict[str, Any] | str | bytes,
        *,
        actor: Any = None,
        dangling_edge_mode: str = "strict",
    ) -> Any:
        """Import a GRIFT document as a collector result and accumulate batch IDs.

        Wraps `tap_grid.grift.grift_import` with all its validation,
        idempotency, and service-layer write semantics. Appends imported and
        skipped batch entity IDs to `self.grift_batches` so the task body can
        persist the full set to `CollectionJob.grift_batches` at terminal state.

        Args:
            document: GRIFT document (parsed dict, JSON string, or bytes).
            actor: Optional User passed through to `grift_import`.
            dangling_edge_mode: Passed through to `grift_import`.

        Returns:
            The raw GriftImportResult; callers may inspect counts / errors /
            warnings directly without going through `self.grift_batches`.
        """
        # Local import keeps tap_grid out of the import-time graph for tap_cares
        # tests that don't need it.
        from tap_grid.grift import grift_import

        result = grift_import(
            document,
            dangling_edge_mode=dangling_edge_mode,  # type: ignore[arg-type]
            actor=actor,
        )

        self.grift_batches["imported"].extend(str(b.batch_entity_id) for b in result.imported_batches)
        self.grift_batches["skipped"].extend(str(b.batch_entity_id) for b in result.skipped_batches)

        return result
