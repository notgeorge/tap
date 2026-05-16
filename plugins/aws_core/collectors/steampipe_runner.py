"""Subprocess boundary for trusted AWS Steampipe query profiles."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from plugins.aws_core.collectors.profiles import CollectionProfile, SteampipeQuery


class SteampipeRunnerError(RuntimeError):
    """Base class for Steampipe runner failures."""


class SteampipeUnavailableError(SteampipeRunnerError):
    """Raised when the Steampipe executable is not available."""


class SteampipeExecutionError(SteampipeRunnerError):
    """Raised when Steampipe exits non-zero."""


class SteampipeJsonError(SteampipeRunnerError):
    """Raised when Steampipe returns invalid JSON."""


@dataclass(frozen=True, slots=True)
class SteampipeQueryResult:
    table: str
    rows: list[dict[str, Any]]
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class SteampipeProfileResult:
    rows_by_table: dict[str, list[dict[str, Any]]]
    warnings: list[str] = field(default_factory=list)

    def row_count(self, table: str) -> int:
        return len(self.rows_by_table.get(table, []))


class SteampipeRunner:
    """Run trusted Steampipe SQL and return JSON rows."""

    def __init__(
        self,
        *,
        binary: str = "steampipe",
        timeout_seconds: int = 120,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds
        self.extra_env = dict(extra_env or {})

    def run_query_set(
        self,
        query_set: CollectionProfile,
        *,
        region: str,
        env: dict[str, str] | None = None,
        redaction_values: tuple[str, ...] = (),
    ) -> SteampipeProfileResult:
        rows_by_table: dict[str, list[dict[str, Any]]] = {}
        warnings: list[str] = []
        for query in query_set.queries:
            result = self.run_query(
                query,
                region=region,
                env=env,
                redaction_values=redaction_values,
            )
            rows_by_table[query.table] = result.rows
            if result.stderr:
                warnings.append(f"{query.table}: {result.stderr}")
        return SteampipeProfileResult(rows_by_table=rows_by_table, warnings=warnings)

    def run_query(
        self,
        query: SteampipeQuery,
        *,
        region: str,
        env: dict[str, str] | None = None,
        redaction_values: tuple[str, ...] = (),
    ) -> SteampipeQueryResult:
        command = [self.binary, "query", query.sql, "--output", "json"]
        run_env = self._build_env(region, env)

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                env=run_env,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise SteampipeUnavailableError(
                f"Steampipe executable {self.binary!r} was not found."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SteampipeExecutionError(
                f"Steampipe query for {query.table} timed out after {self.timeout_seconds}s."
            ) from exc

        stderr = redact_credential_values(
            completed.stderr.strip(),
            extra_values=redaction_values,
        )
        if completed.returncode != 0:
            raise SteampipeExecutionError(
                f"Steampipe query for {query.table} exited {completed.returncode}: {stderr}"
            )

        try:
            rows = _parse_rows(completed.stdout)
        except json.JSONDecodeError as exc:
            raise SteampipeJsonError(
                f"Steampipe query for {query.table} returned invalid JSON."
            ) from exc

        return SteampipeQueryResult(table=query.table, rows=rows, stderr=stderr)

    def _build_env(
        self,
        region: str,
        env: dict[str, str] | None,
    ) -> dict[str, str]:
        run_env = os.environ.copy()
        run_env.update(self.extra_env)
        if env:
            run_env.update(env)
        # Keep regional scope explicit regardless of what the caller's env map
        # carried.
        run_env["AWS_REGION"] = region
        run_env["AWS_DEFAULT_REGION"] = region
        return run_env


def _parse_rows(raw: str) -> list[dict[str, Any]]:
    payload = json.loads(raw)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    else:
        raise SteampipeJsonError("Steampipe JSON output must be a row array or object with rows.")

    if not all(isinstance(row, dict) for row in rows):
        raise SteampipeJsonError("Steampipe JSON rows must be objects.")
    return rows


def redact_credential_values(
    value: str,
    *,
    extra_values: tuple[str, ...] = (),
) -> str:
    """Best-effort redaction for diagnostics before they reach run records."""
    redacted = value
    sensitive_markers = (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "access_key_id",
        "secret_access_key",
        "session_token",
    )
    for marker in sensitive_markers:
        redacted = redacted.replace(marker, "[redacted-key]")
    for secret_value in extra_values:
        if secret_value:
            redacted = redacted.replace(secret_value, "[redacted-value]")
    return redacted
