"""Generated Validation-Map report — the guards describe themselves.

PROTOTYPE of the source-of-truth inversion under discussion: instead of a
hand-maintained prose table in `spec-dev-validation.md`, the live guard set *is*
the record, and this derives a report from it that cannot drift from the code.

`build_report()` enumerates every registered `Guard` and reads the metadata each
already carries (slug, map_row, description, defining module). Optionally it runs
each `check()` and records pass/fail, so the report can show live guard status —
"CI-guarded (passing)" is then a measured fact, not a typed-in claim.

Deliberately kept to what the guards already declare: this does NOT yet add
`rid`/`cadence`/`status` fields or fold in the deliberately-unguarded surfaces
(the negative space the prose Map also tracks). Those are the open design calls;
this is the read-only view that makes the shape concrete first.
"""

from __future__ import annotations

from dataclasses import dataclass

from tap.guards.base import all_guards, validation_map_surfaces


@dataclass(frozen=True)
class GuardRow:
    """One guard, as it describes itself. `passed`/`error` are None unless checks ran."""

    slug: str
    map_row: str
    module: str
    description: str
    in_map: bool
    passed: bool | None
    error: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "map_row": self.map_row,
            "module": self.module,
            "in_map": self.in_map,
            "passed": self.passed,
            "error": self.error,
            "description": self.description,
        }


def build_report(*, run_checks: bool = False) -> list[GuardRow]:
    """Every registered guard as a `GuardRow`, sorted by slug.

    Args:
        run_checks: when True, run each guard's `check()` and record whether it
            passed (and the assertion message if not). Some checks are slow
            (collection-completeness forks pytest), so this is opt-in.
    """
    known_surfaces = validation_map_surfaces()
    rows: list[GuardRow] = []
    for guard in all_guards():
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
                module=type(guard).__module__,
                description=guard.description,
                in_map=guard.map_row in known_surfaces,
                passed=passed,
                error=error,
            )
        )
    return sorted(rows, key=lambda r: r.slug)
