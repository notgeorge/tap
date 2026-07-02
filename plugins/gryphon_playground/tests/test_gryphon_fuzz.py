"""Differential property fuzzer test (Phase 1, the capstone rung).

Seedable random GRIFT graph + random valid query over the model oracle's modeled
surface → executor vs oracle, asserting they agree on identity / row sets. The
oracle (`gridkin/model_oracle.py`) is the differential harness; `gridkin/fuzz.py`
is the generator that turns it into a property fuzzer. See
`plugins/gryphon_playground/specs/spec-gridkin-v0.md` (`req-gridkin-property-fuzz`).

DB-backed and per-graph isolated like `test_gridkin.py`: each parametrized item
seeds one generated graph into a fresh test database, then runs its whole batch
of read-only queries against that single seed (many differentials per truncation
— seeding is the hot spot, queries are cheap).

Bounded and env-tunable so it does not balloon the already-slow gate. For a
longer soak, raise the graph count / batch size or roll the seed:

    GRYPHON_FUZZ_SEED=... GRYPHON_FUZZ_GRAPHS=500 GRYPHON_FUZZ_QUERIES=25 \
        pytest plugins/gryphon_playground/tests/test_gryphon_fuzz.py

A divergence prints the seed + emitted GRIFT + query + both results; the case is
replayable from `random.Random(<graph_seed>)` alone.
"""

from __future__ import annotations

import os

import pytest

from plugins.gryphon_playground.gridkin import fuzz


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


# Committed defaults: 12 graphs × 15 queries = 180 differentials from 12 DB seeds.
_SEED = _env_int("GRYPHON_FUZZ_SEED", 1729)
_N_GRAPHS = _env_int("GRYPHON_FUZZ_GRAPHS", 12)
_QUERIES_PER_GRAPH = _env_int("GRYPHON_FUZZ_QUERIES", 15)

_CASES = fuzz.build_cases(_SEED, _N_GRAPHS, _QUERIES_PER_GRAPH)


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
@pytest.mark.parametrize("case", _CASES, ids=[c.case_id for c in _CASES])
def test_fuzz_executor_matches_oracle(case: fuzz.Case) -> None:
    """Every generated query's executor answer must match the independent oracle.

    A `diverge` or `rejected` outcome fails loudly with a fully replayable report.
    `unmodeled` outcomes are honest skips (never fake greens), but a per-case
    floor fails if the generator drifts so far off the oracle's modeled surface
    that most queries stop being asserted — a vacuous-coverage tripwire, the
    sibling of the metamorphic eligibility floor.
    """
    fuzz.seed_document(case.document)
    outcomes = [fuzz.run_query(case.document, q) for q in case.queries]

    failures = [o for o in outcomes if o.status in ("diverge", "rejected", "crashed")]
    assert not failures, "".join(fuzz.render_failure(case, o) for o in failures)

    asserted = sum(1 for o in outcomes if o.status == "agree")
    floor = max(1, len(case.queries) // 2)
    assert asserted >= floor, (
        f"fuzz coverage collapsed for {case.case_id}: only {asserted}/{len(case.queries)} "
        f"queries were asserted (the rest hit OracleUnmodeled) — the generator has drifted "
        f"off the oracle's modeled surface. Unmodeled samples: "
        f"{[o.detail for o in outcomes if o.status == 'unmodeled'][:3]}"
    )


def test_fuzz_corpus_is_non_trivial() -> None:
    """Guard the generator itself: cases must carry queries to differentiate."""
    assert len(_CASES) >= 1
    assert all(len(c.queries) >= 1 for c in _CASES)
    assert sum(len(c.queries) for c in _CASES) >= 30
