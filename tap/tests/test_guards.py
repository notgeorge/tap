"""Meta-tests over the guard registry — run every guard, and enforce Map completeness.

`test_guard_holds` runs each registered `Guard.check()` as its own parametrized
case (so a failure names the specific guard). `test_guard_is_in_validation_map` is
the fog-killer: it asserts every guard's `map_row` corresponds to a real row in the
Validation Map, so a guard can no longer emerge unaccounted-for (the exact failure
that let direct-write-coverage and json-file-naming exist without a Map row).

Guards are discovered across every owner (`tap/guards/` + each `<app>/guards/` and
`<plugin>/guards/`) by the filesystem walk in `discover_guards()`, so a newly-added
guard file is covered here automatically — no import list to update.
"""

from __future__ import annotations

import pytest

from tap.guards import discover_guards, validation_map_surfaces

_GUARDS = discover_guards()
_IDS = [g.slug for g in _GUARDS]


def test_registry_is_non_empty():
    """Guard against an empty enumeration silently passing the parametrized cases."""
    assert _GUARDS, "no guards discovered — did discover_guards() stop finding a guards/ package?"


@pytest.mark.parametrize("guard", _GUARDS, ids=_IDS)
def test_guard_holds(guard):
    """Every registered guard's invariant holds on the current tree."""
    guard.check()


@pytest.mark.parametrize("guard", _GUARDS, ids=_IDS)
def test_guard_has_description(guard):
    """Every guard states, in-band, why it exists (req: descriptions flow into the structure)."""
    assert guard.description and len(guard.description.strip()) >= 20, (
        f"guard '{guard.slug}' has no (or too thin) `description`. State why the guard is here — "
        f"the failure it prevents — as a first-class field, so the guard set is self-describing."
    )


@pytest.mark.parametrize("guard", _GUARDS, ids=_IDS)
def test_guard_is_in_validation_map(guard):
    """Every guard corresponds to a Validation Map surface (req-dev-validation-map)."""
    surfaces = validation_map_surfaces()
    assert guard.map_row in surfaces, (
        f"guard '{guard.slug}' declares map_row={guard.map_row!r}, which is not a row in the "
        f"Validation Map (specs/spec-dev-validation.md). Add the row in the same change as the "
        f"guard (co-change discipline), or fix the map_row to match an existing surface."
    )


def test_map_parser_is_sane():
    """The completeness check is only as honest as its parse — validate the validator.

    The parser must pick up real surfaces, and must NOT pick up the header, the
    `|---|` separator, or a made-up name.
    """
    surfaces = validation_map_surfaces()
    assert {"Direct-write coverage", "Authz coverage", "Cold-boot system cycle"} <= surfaces
    assert "Surface" not in surfaces  # header row excluded
    assert not any(set(s) <= {"-", " ", ":"} for s in surfaces)  # no separator rows
    assert "Not A Real Surface" not in surfaces
