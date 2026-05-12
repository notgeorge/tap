"""Service helpers for appending structured entries to `CollectionJob.results`.

req-tap-cares-collector-job-model-9 through -16 (spec-tap-cares-collector.md).

Collectors call `record_info` / `record_warn` / `record_error` rather than
mutating `job.results` directly. The helpers:

  1. Build a four-field entry (`site`, `code`, `message`, `context`).
  2. Validate the entry against the pinned schema at
     `tap_cares/schemas/collection_job_results.schema.json`.
  3. Append to `job.results[<level>]`, initializing the level if absent.
  4. Save with `update_fields=["results"]` so concurrently-mutating lifecycle
     fields owned by the task runtime are not clobbered.

The `site` argument is a required positional UUIDv7 hardcoded at each
callsite. Forgetting it raises `TypeError`. A repo-wide test asserts every
record_* callsite has a unique `site` UUID — see
tap_cares/tests/test_results_site_uniqueness.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema

from tap_cares.models import CollectionJob

_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "collection_job_results.schema.json"
_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())
_ENTRY_SCHEMA: dict[str, Any] = _SCHEMA["$defs"]["entry"]

_LEVELS = ("info", "warn", "error")
_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UUIDV7_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _validate_entry(entry: dict[str, Any]) -> None:
    """Validate one entry against the pinned per-entry schema.

    Raises jsonschema.ValidationError on any structural violation. Callers
    should let it propagate — bad entries are programming errors, not
    runtime conditions to swallow.
    """
    jsonschema.validate(instance=entry, schema=_ENTRY_SCHEMA)


def _record(job: CollectionJob, level: str, site: str, code: str, message: str, context: dict[str, Any] | None) -> None:
    if level not in _LEVELS:
        raise ValueError(f"Invalid level {level!r}; expected one of {_LEVELS}.")

    entry = {
        "site": site,
        "code": code,
        "message": message,
        "context": context if context is not None else {},
    }
    _validate_entry(entry)

    # Defensive init in case results was hand-rolled into an empty dict.
    if not isinstance(job.results, dict):
        job.results = {"info": [], "warn": [], "error": []}
    for lvl in _LEVELS:
        job.results.setdefault(lvl, [])

    job.results[level].append(entry)
    job.save(update_fields=["results"])


def record_info(
    job: CollectionJob,
    site: str,
    code: str,
    message: str,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    """Record an informational event on the job.

    Args:
        job: The CollectionJob to record the entry on.
        site: UUIDv7 hardcoded at the callsite (generated via scripts/uuid7).
            Required positional — forgetting it raises TypeError.
        code: Machine-readable category in UPPER_SNAKE.
        message: Human-readable prose specific to this occurrence.
        context: Free-form structured payload. Defaults to {}.
    """
    _record(job, "info", site, code, message, context)


def record_warn(
    job: CollectionJob,
    site: str,
    code: str,
    message: str,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    """Record a warning event on the job.

    Same shape as `record_info`; goes to the `warn` bucket. Reserved for
    non-fatal but notable conditions; v0 KSI does not emit any (every safety
    flag is block-class).
    """
    _record(job, "warn", site, code, message, context)


def record_error(
    job: CollectionJob,
    site: str,
    code: str,
    message: str,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    """Record an error event on the job.

    Same shape as `record_info`; goes to the `error` bucket. Block-class
    safety flags and terminal failures call this. The task runtime sets
    `CollectionJob.error_summary` separately for the at-a-glance one-liner.
    """
    _record(job, "error", site, code, message, context)
