"""Durable per-run boot record (req-boot-obs-record).

Every `manage.py boot` run writes one machine-legible JSON document describing
what happened — success or abort — under the instance's visible runtime-log dir
(`logs/boot/`, gitignored; worktree-visible in dev). The record, not terminal
scrollback, is the post-hoc evidence: the `/diagnose-failed-session-spawn`
skill, the spawn presenter, and integrated AI assistants read it instead of
re-running boot.

Write discipline:

- **Incremental + atomic.** The document is rewritten (temp file + `os.replace`)
  at every phase/step boundary, so a killed or aborted boot still leaves the
  record through its last completed boundary (req-boot-obs-record-2).
- **Never load-bearing.** A record-write failure must not take the standup down:
  the first `OSError` logs a WARNING and disables further writes for the run.
- **Secret-free.** The record carries values-with-provenance for boot variables
  and self-test check payloads only; secrets never enter it
  (req-boot-obs-record-5 — the check payloads are redaction-safe by the
  collector contract, req-tap-cares-collector-self-test-13).

The document shape is described by `tap_boot/schemas/boot-record.schema.json`
(spec-tap-json-files.md). Spec: specs/spec-tap-boot-observability.md.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["BootRecord", "NullBootRecord", "maybe_boot_record"]

RECORD_VERSION = 1
LATEST_BASENAME = "latest.boot-record.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class NullBootRecord:
    """No-op stand-in so orchestration code never branches on record presence.

    Used when no record is wanted (the test runner's repeated in-process boots
    would litter the worktree; tests that assert on the record pass a real
    `BootRecord` with a scratch `base_dir`).
    """

    def record_variable(self, section: str, key: str, value: Any, source: str) -> None:
        return

    def record_step(self, entry: dict[str, Any]) -> None:
        return

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        yield

    def finish_ok(self) -> None:
        return

    def finish_aborted(self, domain: str, reason: str, *, data: dict[str, Any] | None = None) -> None:
        return


class BootRecord(NullBootRecord):
    """Incremental writer for one boot run's record (req-boot-obs-record-1/-2)."""

    def __init__(self, profile_id: str | None, *, base_dir: Path | str | None = None) -> None:
        from django.conf import settings

        self.run_id = str(uuid.uuid7())
        base = Path(base_dir) if base_dir is not None else Path(settings.BASE_DIR)
        self._dir = base / "logs" / "boot"
        self.path = self._dir / f"{self.run_id}.boot-record.json"
        self._latest = self._dir / LATEST_BASENAME
        self._broken = False
        self._data: dict[str, Any] = {
            "record_version": RECORD_VERSION,
            "run_id": self.run_id,
            "grid_id": getattr(settings, "TAP_GRID_ID", "") or "",
            "profile": profile_id,
            "started_at": _now(),
            "finished_at": None,
            "outcome": "running",
            "abort": None,
            "variables": [],
            "phases": [],
            "steps": [],
        }
        self._flush()

    def record_variable(self, section: str, key: str, value: Any, source: str) -> None:
        """One resolved boot variable with provenance (req-boot-obs-record-3)."""
        self._data["variables"].append({"section": section, "key": key, "value": value, "source": source})
        self._flush()

    def record_step(self, entry: dict[str, Any]) -> None:
        """One population/preflight step outcome, appended in execution order."""
        self._data["steps"].append(entry)
        self._flush()

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Bracket one boot phase; a raising phase is finalized as failed."""
        entry: dict[str, Any] = {"phase": name, "status": "running", "started_at": _now(), "finished_at": None}
        self._data["phases"].append(entry)
        self._flush()
        try:
            yield
        except BaseException:
            entry["status"] = "failed"
            entry["finished_at"] = _now()
            self._flush()
            raise
        entry["status"] = "ok"
        entry["finished_at"] = _now()
        self._flush()

    def finish_ok(self) -> None:
        self._data["outcome"] = "ok"
        self._data["finished_at"] = _now()
        self._flush()

    def finish_aborted(self, domain: str, reason: str, *, data: dict[str, Any] | None = None) -> None:
        self._data["outcome"] = "aborted"
        self._data["finished_at"] = _now()
        self._data["abort"] = {"domain": domain, "reason": reason, **(data or {})}
        self._flush()

    def _flush(self) -> None:
        """Atomically rewrite the per-run file and the `latest` pointer.

        Two independent atomic replaces (temp file + `os.replace` in the same
        directory, so the rename never crosses a filesystem boundary). Failure
        disables the record for the rest of the run — observability must never
        take the standup down.
        """
        if self._broken:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._data, indent=2, default=str)
            for target in (self.path, self._latest):
                fd, tmp_name = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
                try:
                    with os.fdopen(fd, "w") as fh:
                        fh.write(payload)
                    os.replace(tmp_name, target)
                except BaseException:
                    Path(tmp_name).unlink(missing_ok=True)
                    raise
        except OSError:
            self._broken = True
            logger.warning("[cbe0] boot record disabled for this run: cannot write %s", self.path, exc_info=True)


def maybe_boot_record(profile_id: str | None) -> BootRecord | NullBootRecord:
    """A real record in normal operation; a no-op one under the test runner.

    The test suite drives `run_boot` directly and repeatedly against the mounted
    worktree — writing a record per test would litter `logs/boot/`. Keyed on the
    deploy-controlled `TAP_TEST_MODE` settings flag, the same trusted carve as
    the boot invocation self-check.
    """
    from django.conf import settings

    if getattr(settings, "TAP_TEST_MODE", False):
        return NullBootRecord()
    return BootRecord(profile_id)
