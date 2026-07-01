"""Metamorphic relations over the Gryphon corpus (Phase 3, after SQLancer).

Each eligible scenario is transformed into related queries that MUST agree, and
the executor is compared against *itself* — catching common-mode bugs the model
oracle could share and exercising cross-dispatch-path consistency a single-query
check cannot. See `gridkin/metamorphic.py` for the relations and the load-bearing
2VL/3VL null discriminator.

DB-backed and per-scenario isolated, like `test_gridkin.py`: each parametrized
item seeds its scenario's fixture into a fresh test database, then runs the
derived queries. Only eligible scenarios are parametrized; ineligible shapes are
simply not emitted (honest partial coverage — the counts are asserted below so a
regression to zero-eligible fails loudly).
"""

from __future__ import annotations

import pytest

from plugins.gryphon_playground.gridkin import loader, metamorphic
from plugins.gryphon_playground.gridkin.runner import _seed_fixture
from tap_grid.gryphon import explain_gryphon_raw

_SCENARIOS = loader.discover_scenarios()
_TLP = [(s, plan) for s in _SCENARIOS if (plan := metamorphic.derive_tlp(s)) is not None]


def _row_ids(scenario, query: str) -> frozenset[str]:
    """Run an entity-id projection query; return the set of projected ids."""
    result = explain_gryphon_raw(  # TAP-AUTHZ-COV: pytest-only metamorphic harness, not a production path
        query, scenario.params, db_alias="default", layer=scenario.layer
    )
    return frozenset(row["id"] for row in result["envelope"].get("rows", []))


def test_metamorphic_corpus_is_non_trivially_covered():
    # Guard against silent erosion: if a refactor makes every scenario ineligible
    # (a derivation bug, or the corpus losing its type-scan WHERE shapes), the TLP
    # check would vacuously pass. Pin a floor.
    assert len(_TLP) >= 30, f"TLP eligibility collapsed to {len(_TLP)} — derivation regression?"


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
@pytest.mark.parametrize("scenario,plan", _TLP, ids=[s.scenario_id for s, _ in _TLP])
def test_tlp_partitions_the_unfiltered_set(scenario, plan):
    """TRUE / FALSE / (UNKNOWN) partition the unfiltered scan — disjoint and total.

    The UNKNOWN partition exists iff the predicate can be UNKNOWN (3VL null field).
    For a 2VL null-literal operand the predicate is genuine-FALSE, so there is no
    UNKNOWN partition and the TRUE partition must be empty.
    """
    _seed_fixture(scenario)

    unfiltered = _row_ids(scenario, plan.unfiltered_query)
    partitions = {
        "TRUE": _row_ids(scenario, plan.true_query),
        "FALSE": _row_ids(scenario, plan.false_query),
    }
    if plan.unknown_query is not None:
        partitions["UNKNOWN"] = _row_ids(scenario, plan.unknown_query)

    union = frozenset().union(*partitions.values())
    assert union == unfiltered, (
        "TLP partitions do not reconstruct the unfiltered scan:\n"
        f"  missing (in unfiltered, no partition): {sorted(unfiltered - union)}\n"
        f"  extra (in a partition, not unfiltered): {sorted(union - unfiltered)}\n"
        f"  queries: {plan}"
    )

    keys = list(partitions)
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            overlap = partitions[left] & partitions[right]
            assert not overlap, (
                f"TLP partitions {left} and {right} overlap (a row in two truth "
                f"classes — a 2VL/3VL discriminator bug): {sorted(overlap)}\n  queries: {plan}"
            )

    if plan.is_two_valued:
        assert not partitions["TRUE"], (
            "2VL null-literal operand: `field OP null` is genuine FALSE, so the TRUE "
            f"partition must be empty, got {sorted(partitions['TRUE'])}\n  queries: {plan}"
        )
