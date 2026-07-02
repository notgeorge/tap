"""Long-running Gryphon fuzz *campaign* — the measurement engine behind the
bug-frequency trend (`scripts/gryphon-fuzz-campaign`).

This is NOT a gate. The per-commit gate is `test_gryphon_fuzz.py`, which asserts
a small committed band agrees and fails on any divergence. This module is its
long-soak complement: it grinds a large, *fresh* seed band (advanced past every
prior campaign so it never re-tests fixed territory — the whole point, since
divergences are deterministic and a fixed seed never re-fires), classifies every
query via `fuzz.run_query` WITHOUT asserting, and writes a machine-readable
campaign summary. The bash orchestrator stamps it with the commit + UTC, appends
it to an append-only JSONL ledger, and prints the trend.

The metric that trends **down-and-to-the-right** as the executor hardens is
*distinct new defects per 100k queries over fresh seed space* — with the
oracle-*asserted fraction* recorded alongside so a falling defect rate cannot be
faked by the generator drifting off the modeled surface (bugs→0 must mean
"hardened", not "stopped exploring"). See `spec-gridkin-v0.md`
(`req-gridkin-fuzz-campaign`) and the Validation Map in `spec-dev-validation.md`.

DB isolation is inherited verbatim from `test_gryphon_fuzz.py`: one
`transaction=True` parametrized item per graph, so each graph seeds a truncated
database (search_readonly shares the physical DB, so seeds must commit to be
visible — the reason rollback isolation will not work here).

Activated only when `GRYPHON_FUZZ_CAMPAIGN_OUT` names a summary path; otherwise
the module is skipped so a normal `pytest` run neither builds a band nor grinds.
Env knobs (all read by the orchestrator):

    GRYPHON_FUZZ_CAMPAIGN_BASE     first seed of the band (orchestrator advances it)
    GRYPHON_FUZZ_CAMPAIGN_GRAPHS   graphs in the band (default 50)
    GRYPHON_FUZZ_CAMPAIGN_QUERIES  queries per graph (default 25)
    GRYPHON_FUZZ_CAMPAIGN_OUT      path to write the summary JSON (required to run)
"""

from __future__ import annotations

import json
import os
import re

import pytest

from plugins.gryphon_playground.gridkin import fuzz

# Activated only when a summary path is named (set by scripts/gryphon-fuzz-campaign).
# A NORMAL pytest run leaves it unset — the test is then COLLECTED but skips at
# call time (a function-level skipif, NOT a module-level skip). Module-level skip
# would collect zero node ids, which the collection-completeness guard
# (`tap/tests/test_collection_completeness.py`, req-dev-validation-collection-complete)
# correctly flags as an uncollected orphan. So the file always contributes an item.
_OUT = os.environ.get("GRYPHON_FUZZ_CAMPAIGN_OUT", "").strip()
_ACTIVE = bool(_OUT)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


_BASE = _env_int("GRYPHON_FUZZ_CAMPAIGN_BASE", 1_000_000)
_GRAPHS = _env_int("GRYPHON_FUZZ_CAMPAIGN_GRAPHS", 50)
_QUERIES = _env_int("GRYPHON_FUZZ_CAMPAIGN_QUERIES", 25)

# Build the real band only when a campaign is requested; otherwise a single
# placeholder so the file still collects one (skipped) item.
if _ACTIVE:
    _CASES: list = fuzz.build_cases(_BASE, _GRAPHS, _QUERIES)
    _IDS = [c.case_id for c in _CASES]
else:
    _CASES = [None]
    _IDS = ["campaign-disabled"]

# Accumulates across the parametrized graph items; the module-teardown fixture
# reduces it to one summary. A defect (diverge / rejected / crashed) is a
# `(graph_seed, QueryOutcome)`; agree/unmodeled contribute only to the totals.
_OUTCOMES: list[tuple[int, fuzz.QueryOutcome]] = []


def _fingerprint(oc: fuzz.QueryOutcome) -> str:
    """A defect fingerprint: query SHAPE + status (+ exception type for crashes).

    Literals, params, numbers, and type labels are normalized away so distinct
    seeds that trip the *same* underlying defect collapse to one fingerprint —
    the campaign counts distinct defects, not instances.
    """
    shape = oc.query
    shape = re.sub(r'"[^"]*"', '"S"', shape)  # string literals / needles
    shape = re.sub(r"\$[A-Za-z_][A-Za-z0-9_]*", "$P", shape)  # params
    shape = re.sub(r"\b\d+\b", "N", shape)  # numeric literals
    shape = re.sub(r"gryphon_playground__pg_\w+", "L", shape)  # node type labels
    shape = re.sub(r"\s+", " ", shape).strip()
    sig = f"{oc.status}|{shape}"
    if oc.status == "crashed":
        sig += "|" + oc.detail.split(":", 1)[0]  # exception class
    return sig


@pytest.fixture(scope="module", autouse=True)
def _write_campaign_summary():
    yield
    if not _ACTIVE:
        return  # no campaign requested — nothing collected ran, nothing to write
    totals: dict[str, int] = {"agree": 0, "diverge": 0, "rejected": 0, "crashed": 0, "unmodeled": 0}
    fingerprints: dict[str, dict[str, object]] = {}
    for seed, oc in _OUTCOMES:
        totals[oc.status] = totals.get(oc.status, 0) + 1
        if oc.status in ("diverge", "rejected", "crashed"):
            fp = _fingerprint(oc)
            # Keep the first instance of each fingerprint for triage/replay.
            fingerprints.setdefault(fp, {"seed": seed, "query": oc.query, "detail": oc.detail[:400]})
    n_queries = sum(totals.values())
    asserted = totals["agree"] + totals["diverge"]
    summary = {
        "base_seed": _BASE,
        "seed_end": _BASE + _GRAPHS - 1,
        "n_graphs": _GRAPHS,
        "queries_per_graph": _QUERIES,
        "n_queries": n_queries,
        "totals": totals,
        # Oracle-asserted share — the denominator that keeps a falling defect
        # rate honest (a low rate with a low asserted fraction is exploration
        # collapse, not hardening).
        "asserted_fraction": round(asserted / n_queries, 4) if n_queries else 0.0,
        "distinct_defects": len(fingerprints),
        "defects": [{"fingerprint": fp, **info} for fp, info in sorted(fingerprints.items())],
    }
    with open(_OUT, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)


@pytest.mark.skipif(not _ACTIVE, reason="fuzz campaign not requested; run via scripts/gryphon-fuzz-campaign")
@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_campaign_graph(case: fuzz.Case) -> None:
    """Grind one fresh graph; record every query outcome. Never asserts.

    A seeding failure is itself recorded (as a `crashed` outcome) rather than
    aborting the campaign — the run must complete the whole band and write the
    ledger summary so the trend advances even when a generated fixture is bad.
    """
    try:
        fuzz.seed_document(case.document)
    except Exception as exc:  # noqa: BLE001 — a bad generated fixture is a finding, not a harness abort
        _OUTCOMES.append((case.graph_seed, fuzz.QueryOutcome("<seed>", "crashed", f"{type(exc).__name__}: {exc}")))
        return
    for q in case.queries:
        _OUTCOMES.append((case.graph_seed, fuzz.run_query(case.document, q)))
