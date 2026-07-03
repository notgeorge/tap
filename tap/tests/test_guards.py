"""Meta-tests over the guard registry — run every guard, and keep the Map honest.

`test_guard_holds` runs each registered `Guard.check()` as its own parametrized
case (so a failure names the specific guard). `test_guard_rid_resolves` is the
fog-killer: it asserts every guard's `rid` resolves to a requirement *actually
defined* in some spec, so a guard can no longer emerge pointing at a non-existent
requirement (the inverted successor to the old "map_row ∈ prose table" check —
requirements are the authored edge; the Map is generated). `test_spec_map_in_sync`
asserts the generated Map block committed in the spec equals what the code produces,
so the two cannot drift.

Guards are discovered across every owner (`tap/guards/` + each `<app>/guards/` and
`<plugin>/guards/`) by the filesystem walk in `discover_guards()`, so a newly-added
guard file is covered here automatically — no import list to update.
"""

from __future__ import annotations

import pytest

from tap.guards import defined_requirement_rids, discover_guards
from tap.guards.base import REPO_ROOT
from tap.guards.report import MAP_BEGIN, MAP_END, render_map_markdown
from tap.guards.surfaces import DECLARED_SURFACES

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
def test_guard_rid_resolves(guard):
    """Every guard's `rid` resolves to a real, defined requirement (req-dev-validation-map-6)."""
    defined = defined_requirement_rids()
    assert guard.rid, f"guard '{guard.slug}' declares no `rid` — link it to the requirement it enforces."
    assert guard.rid in defined, (
        f"guard '{guard.slug}' declares rid={guard.rid!r}, which is not a requirement defined in any "
        f"spec (an `RID:` heading or a requirements-table cell — an inline reference does not count). "
        f"Point it at a real requirement, or define the requirement in the same change."
    )


@pytest.mark.parametrize("surface", DECLARED_SURFACES, ids=[s.surface for s in DECLARED_SURFACES])
def test_declared_surface_rid_resolves(surface):
    """Every declared (non-guard) surface's `rid` resolves too — the negative space stays honest."""
    defined = defined_requirement_rids()
    assert surface.rid in defined, (
        f"declared surface {surface.surface!r} points at rid={surface.rid!r}, which is not defined in "
        f"any spec. Fix the rid in tap/guards/surfaces.py or define the requirement."
    )


def test_rid_resolver_is_sane():
    """Validate the validator: the resolver must accept real RIDs and reject non-RIDs.

    A too-loose resolver would let a dangling rid pass — the exact failure this
    inversion exists to prevent (`req-dev-validation-mypy-ratchet` was referenced but
    undefined under the old prose Map).
    """
    defined = defined_requirement_rids()
    assert {"req-dev-validation-smoke-gate", "req-tap-auth-policy-9"} <= defined
    assert "req-does-not-exist-anywhere" not in defined
    assert "Surface" not in defined  # a table header cell is not an RID


def test_spec_map_in_sync():
    """The generated Map block committed in the spec equals `render_map_markdown()` (req-dev-validation-map-5).

    Guarantees the committed inventory cannot drift from the guards + declared
    surfaces. If this fails, run `manage.py guards --sync-map` and review the diff.
    """
    spec_text = (REPO_ROOT / "specs" / "spec-dev-validation.md").read_text(encoding="utf-8")
    begin = spec_text.find(MAP_BEGIN)
    end = spec_text.find(MAP_END)
    assert begin != -1 and end != -1, "generated Map markers missing from spec-dev-validation.md"
    committed = spec_text[begin : end + len(MAP_END)]
    assert committed == render_map_markdown(), (
        "The generated Map block in spec-dev-validation.md is out of sync with the guards + "
        "DECLARED_SURFACES. Run `manage.py guards --sync-map` and commit the result."
    )
