"""Probe selection sets — which probes answer which operational question.

req-tap-health-selection (spec-tap-health-v0.md).

A probe declares the named sets it belongs to at registration
(``sets=("readiness",)``); a caller names the set it wants
(``run_health(selection="readiness")``). Membership is **multi-valued** — a probe
may belong to several sets — because the same probe legitimately answers more
than one question, and a single-membership field could not express that
(the prior-art lesson recorded in req-tap-health-probe-registry-8: Spring Boot
health groups / ASP.NET tags, both distinct from a probe's owning ``group``).

`group` remains ownership/clustering (which app contributed the probe);
`sets` is selection. They are orthogonal, as is `critical`: `queue` is a
readiness member that is NOT critical, and `secrets` is critical while choosing
its own degraded-vs-unhealthy status.

Why `liveness` is deliberately (near-)empty
-------------------------------------------
Liveness answers exactly one question: **would restarting this process fix it?**
Every probe registered today checks a *dependency* — Postgres, the cache table,
the migration state, secret material on disk. Restarting the web container fixes
none of those, so classifying them as liveness would convert a database outage
into a restart loop (the well-documented Kubernetes anti-pattern of putting
dependencies in a liveness probe). An honest near-empty liveness set is better
than a plausible-looking one that kills healthy containers, so this module
defines the vocabulary without populating it.

A selection that resolves to zero probes therefore reports `unknown` — "nothing
answered this question" — never `healthy`, which would be a green light earned
by checking nothing (Law 1, Preserve Truth, docs/misc/agent-affordance-laws.md).
For liveness that is also the correct fail-safe: unknown keeps `ok` True, so an
orchestrator does not restart on the strength of a question nobody can answer.

Plugin-defined sets are backlogged: the declarable vocabulary is closed to
`DECLARABLE_SETS` today, and an unknown tag is a loud startup error rather than
a silently-ignored string.
"""

from __future__ import annotations

from dataclasses import dataclass

LIVENESS = "liveness"
READINESS = "readiness"
ALL = "all"


@dataclass(frozen=True)
class ProbeSelection:
    """A named selection set: the operational question it answers."""

    name: str
    description: str


STANDARD_SELECTIONS: tuple[ProbeSelection, ...] = (
    ProbeSelection(
        LIVENESS,
        "Would restarting this process fix it? Deliberately near-empty: dependency "
        "failures (db, cache, migrations, secrets) are not restart-fixable.",
    ),
    ProbeSelection(
        READINESS,
        "Is this instance fit to serve and to act on the grid? The set the spawn gate and CI boot gates poll.",
    ),
    ProbeSelection(
        ALL,
        "Every registered probe regardless of its declared sets. Reserved: it is "
        "implicit membership, never declared on a probe.",
    ),
)

# Sets a probe may declare. `ALL` is reserved (implicit), so it is not here.
DECLARABLE_SETS: frozenset[str] = frozenset({LIVENESS, READINESS})

SELECTION_NAMES: tuple[str, ...] = tuple(s.name for s in STANDARD_SELECTIONS)

_BY_NAME: dict[str, ProbeSelection] = {s.name: s for s in STANDARD_SELECTIONS}


def resolve_selection(name: str) -> ProbeSelection:
    """Resolve a selection name, or raise `ValueError` naming the valid options.

    Args:
        name: The selection to run (`liveness`, `readiness`, or `all`).

    Returns:
        The `ProbeSelection` record.

    Raises:
        ValueError: The name is not a known selection. The message lists the
            valid names — a caller (human or agent) learns the vocabulary from
            the refusal rather than guessing at a default.
    """
    try:
        return _BY_NAME[name]
    except KeyError:
        valid = ", ".join(SELECTION_NAMES)
        raise ValueError(f"Unknown health selection {name!r}. Valid selections: {valid}.") from None


def validate_declared_sets(probe_name: str, sets: tuple[str, ...]) -> None:
    """Validate the sets a probe declares at registration.

    Declaration is mandatory and closed: a probe that declares nothing, or that
    declares an unknown tag, is a startup error rather than a probe that quietly
    joins (or misses) the gate that guards a deploy.

    Args:
        probe_name: The probe being registered (for the error message).
        sets: The declared set names.

    Raises:
        django.core.exceptions.ImproperlyConfigured: Empty, unknown, or reserved.
    """
    from django.core.exceptions import ImproperlyConfigured

    declarable = ", ".join(sorted(DECLARABLE_SETS))
    if not sets:
        raise ImproperlyConfigured(
            f"Health probe {probe_name!r} declared no selection sets. Declare at least one of: "
            f"{declarable}. (Membership is explicit by design — an undeclared probe would "
            f"silently join or miss the readiness gate.)"
        )
    if ALL in sets:
        raise ImproperlyConfigured(
            f"Health probe {probe_name!r} declared the reserved set {ALL!r}. Every probe is in "
            f"{ALL!r} implicitly; declare the specific sets it answers for: {declarable}."
        )
    unknown = sorted(set(sets) - DECLARABLE_SETS)
    if unknown:
        raise ImproperlyConfigured(
            f"Health probe {probe_name!r} declared unknown selection set(s) {unknown}. "
            f"Declarable sets are: {declarable}. (Plugin-defined sets are not supported yet.)"
        )


def selects(declared_sets: tuple[str, ...], selection: str) -> bool:
    """Whether a probe with `declared_sets` runs under `selection`."""
    return selection == ALL or selection in declared_sets


__all__ = [
    "ALL",
    "DECLARABLE_SETS",
    "LIVENESS",
    "READINESS",
    "SELECTION_NAMES",
    "STANDARD_SELECTIONS",
    "ProbeSelection",
    "resolve_selection",
    "selects",
    "validate_declared_sets",
]
