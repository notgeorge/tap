"""Generated Validation Map — the guards and declared surfaces describe themselves.

This is the source-of-truth inversion: instead of a hand-maintained prose table in
`spec-dev-validation.md`, the live guard set *is* the record for guarded surfaces,
and `tap.guards.surfaces.DECLARED_SURFACES` carries the negative space (behavioral
suites, gates, manual/deferred procedures). `render_map_markdown()` derives the Map
table from both, so the committed table cannot drift from the code — a meta-test
(`test_spec_map_in_sync`) asserts the spec block equals this output, and
`manage.py guards --sync-map` regenerates it.

`build_report()` additionally enumerates every registered `Guard` with the metadata
each carries (slug, map_row, rid, cadence, status, description, defining module) and,
optionally, a live `check()` pass/fail — so `manage.py guards --check` shows measured
status, not a typed-in claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from tap.guards.base import Guard, defined_requirement_rids
from tap.guards.discovery import discover_guards
from tap.guards.surfaces import DECLARED_SURFACES

# Markers delimiting the generated Map block inside spec-dev-validation.md. The text
# between them is owned by `render_map_markdown()`; edits belong in the guards /
# DECLARED_SURFACES, then `manage.py guards --sync-map`.
MAP_BEGIN = "<!-- BEGIN GENERATED MAP — manage.py guards --sync-map -->"
MAP_END = "<!-- END GENERATED MAP -->"


@dataclass(frozen=True)
class GuardRow:
    """One guard, as it describes itself. `passed`/`error` are None unless checks ran."""

    slug: str
    map_row: str
    rid: str
    cadence: str
    status: str
    module: str
    description: str
    rid_resolves: bool
    passed: bool | None
    error: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "map_row": self.map_row,
            "rid": self.rid,
            "cadence": self.cadence,
            "status": self.status,
            "module": self.module,
            "rid_resolves": self.rid_resolves,
            "passed": self.passed,
            "error": self.error,
            "description": self.description,
        }


def build_report(*, run_checks: bool = False) -> list[GuardRow]:
    """Every registered guard as a `GuardRow`, sorted by slug.

    Args:
        run_checks: when True, run each guard's `check()` and record whether it
            passed (and the assertion message if not). Some checks are slow
            (collection-completeness forks pytest; mypy runs the type checker), so
            this is opt-in.
    """
    defined = defined_requirement_rids()
    rows: list[GuardRow] = []
    for guard in discover_guards():
        passed: bool | None = None
        error: str | None = None
        if run_checks:
            try:
                guard.check()
                passed = True
            except AssertionError as exc:
                passed = False
                error = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        rows.append(
            GuardRow(
                slug=guard.slug,
                map_row=guard.map_row,
                rid=guard.rid,
                cadence=guard.cadence,
                status=guard.status,
                module=type(guard).__module__,
                description=guard.description,
                rid_resolves=guard.rid in defined,
                passed=passed,
                error=error,
            )
        )
    return sorted(rows, key=lambda r: r.slug)


@dataclass(frozen=True)
class MapRow:
    """One Validation Map inventory row (a guarded surface or a declared surface)."""

    surface: str
    rid: str
    cadence: str
    status: str
    enforced_by: str


def _guard_map_rows() -> list[MapRow]:
    """Guards grouped by `map_row` — one inventory row per surface.

    Several guards can protect one surface (three log-site guards, two collection
    guards); they share rid/cadence/status, so the group collapses to a single row
    whose "Enforced by" lists each defining module.
    """
    by_surface: dict[str, list[Guard]] = {}
    for guard in discover_guards():
        by_surface.setdefault(guard.map_row, []).append(guard)

    rows: list[MapRow] = []
    for surface, guards in by_surface.items():
        first = guards[0]
        modules = sorted({f"`{type(g).__module__}`" for g in guards})
        rows.append(
            MapRow(
                surface=surface,
                rid=first.rid,
                cadence=first.cadence,
                status=first.status,
                enforced_by=", ".join(modules) + " (via `tap/tests/test_guards.py`)",
            )
        )
    return rows


def map_rows() -> list[MapRow]:
    """The full Map: guarded surfaces (from the guards) ∪ declared surfaces, sorted by name."""
    rows = _guard_map_rows()
    rows += [
        MapRow(
            surface=s.surface,
            rid=s.rid,
            cadence=s.cadence,
            status=s.status,
            enforced_by=s.enforced_by,
        )
        for s in DECLARED_SURFACES
    ]
    return sorted(rows, key=lambda r: r.surface.lower())


def render_map_markdown() -> str:
    """The generated Map table, wrapped in the BEGIN/END markers (no trailing newline)."""
    header = (
        "| Surface | Requirement | Cadence | Status | Enforced by |\n"
        "| --- | --- | --- | --- | --- |"
    )
    lines = [
        f"| {r.surface} | `{r.rid}` | {r.cadence} | {r.status} | {r.enforced_by} |"
        for r in map_rows()
    ]
    return "\n".join([MAP_BEGIN, "", header, *lines, "", MAP_END])
