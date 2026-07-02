"""Findings ledger — WHERE bugs live in the Gryphon executor, for hotspot-driven refactor.

The sibling of the fuzz-campaign ledger (`fuzz_campaign.py`). The campaign tracks
bug **frequency over time** (trending down as the executor hardens); this tracks
bug **locality** — which part of the executor concentrates defects — so the hot
spots become the refactor / simplification targets (`req-gridkin-findings-ledger`).

One append-only JSONL row per root-caused executor/oracle defect, human-authored
at fix time (riding the existing "every bug earns a regression scenario"
discipline). The load-bearing field is `subsystem`: a small STRUCTURAL vocabulary
(each subsystem is a set of executor functions), so the same key drives both the
hotspot histogram AND the coverage column. Conceptual concerns that cut across
functions (null semantics, the 2VL/3VL boundary) are `tags`, a secondary lens.

**The honesty guard (do not drop it):** found-bug hotspots are biased toward
where we have LOOKED. A subsystem with zero findings may be under-tested, not
clean. So the report pairs each subsystem's finding count with its line coverage
(from the branch-coverage ratchet's JSON, when available): high-coverage +
high-findings = a genuine hotspot; low-coverage + low-findings = a blind spot, not
a clean bill. Read the two columns together — the same honest-denominator move as
the campaign's asserted-fraction.

Stdlib-only (like `fuzz_campaign.py`): the reporter parses `executor.py` with
`ast` for function line spans and reads the coverage JSON as a file; it never
imports Django or the executor, so `scripts/gryphon-findings` renders it
in-container without app setup.
"""

from __future__ import annotations

import ast
import json
import os
from collections import Counter
from typing import Any

# ---------------------------------------------------------------------------
# Structural subsystem vocabulary — each maps to a set of executor.py functions.
# The map is authoritative: it drives the hotspot histogram AND (via each
# function's AST line span) the coverage column. Adding an executor subsystem is
# a visible edit here. `oracle` covers the reference impl (model_oracle.py), a
# different file — its findings are counted but carry no executor coverage number.
# ---------------------------------------------------------------------------

SUBSYSTEMS: dict[str, str] = {
    "dispatch-routing": "AST → execution-mode dispatch (which executor path a query takes)",
    "chain-join": "Multi-hop Edge queryset construction (reverse-FK joins, hop paths, bindings)",
    "predicate-lowering": "WHERE predicate tree → Django Q (comparisons, combinators, guards)",
    "field-path-resolution": "Gryphon FieldPath → ORM lookup path (spine / data / dimensions lanes)",
    "envelope-collection": "Graph-envelope assembly (nodes + connecting edges) from a chain qs",
    "row-aggregation": "RETURN row projection + COUNT aggregation",
    "type-scan": "Node-only type-scan execution (labelled + bare labelless)",
    "type-strictness": "Data-lane literal-type enforcement before lowering",
    "optional-match": "OPTIONAL MATCH left-outer-join scoreboard",
    "not-exists": "NOT EXISTS correlated anti-join",
    "serialization": "Entity/edge node + edge serialization at a subgraph layer",
    "oracle": "The independent reference oracle (model_oracle.py) — bugs in the checker itself",
}

# function name -> subsystem. Only executor.py module-level functions; the coverage
# column sums line coverage over each subsystem's functions. Not exhaustive — an
# unmapped function's lines simply don't count toward any subsystem's coverage.
FUNCTION_SUBSYSTEM: dict[str, str] = {
    # dispatch-routing
    "_execute_gryphon_raw_impl": "dispatch-routing",
    "_execute_ast": "dispatch-routing",
    "_dispatch_pattern": "dispatch-routing",
    "_has_advanced_features": "dispatch-routing",
    # chain-join
    "_build_chain_queryset": "chain-join",
    "_build_clause_queryset": "chain-join",
    "_compute_hop_paths": "chain-join",
    "_build_var_bindings": "chain-join",
    # predicate-lowering
    "_predicate_to_q": "predicate-lowering",
    "_comparison_to_q": "predicate-lowering",
    "_chain_predicate_q": "predicate-lowering",
    "_apply_predicate_to_qs": "predicate-lowering",
    "_flatten_conjunction": "predicate-lowering",
    "_guard_negated_far_predicate": "predicate-lowering",
    "_binding_is_multivalued_hop": "predicate-lowering",
    "_filter_predicate_for_bindings": "predicate-lowering",
    # field-path-resolution
    "_resolve_orm_path": "field-path-resolution",
    "_orm_path_for_field": "field-path-resolution",
    "_orm_path_for_envelope_path": "field-path-resolution",
    "_typescan_orm_path": "field-path-resolution",
    # envelope-collection
    "_collect_graph_envelope": "envelope-collection",
    "_execute_single_hop_envelope": "envelope-collection",
    "_single_hop_directed": "envelope-collection",
    "_merge_envelopes": "envelope-collection",
    # row-aggregation
    "_compute_rows": "row-aggregation",
    "_resolve_order_cols": "row-aggregation",
    # type-scan
    "_execute_type_scan": "type-scan",
    "_execute_bare_type_scan": "type-scan",
    "_apply_typescan_predicate": "type-scan",
    # type-strictness
    "_enforce_type_strictness": "type-strictness",
    "_declared_data_types": "type-strictness",
    "_admits": "type-strictness",
    # optional-match
    "_execute_optional_match": "optional-match",
    "_count_optional_edges": "optional-match",
    # not-exists
    "_apply_not_exists": "not-exists",
    # serialization
    "_serialize_entity_nodes": "serialization",
    "_serialize_typed_nodes": "serialization",
    "_serialize_edge_list": "serialization",
}

_CLASSES = frozenset({"silent-wrong-answer", "crash", "over-rejection", "oracle-bug"})
_SOURCES = frozenset(
    {"campaign", "fuzz-gate", "model-oracle", "gridkin-authoring", "metamorphic", "manual-usage", "review"}
)
_REQUIRED = ("id", "date", "symptom", "class", "subsystem", "functions", "discovery", "fix_commit")


class LedgerError(ValueError):
    """A findings-ledger row is malformed or violates the controlled vocabulary."""


def load(path: str) -> list[dict[str, Any]]:
    """Load every finding from the JSONL ledger (missing file → empty list)."""
    if not os.path.exists(path):
        return []
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise LedgerError(f"line {i}: invalid JSON: {exc}") from exc
    return rows


def validate(rows: list[dict[str, Any]]) -> None:
    """Assert every row is well-formed and uses the controlled vocabulary.

    Function names are NOT asserted to still exist in executor.py: a finding is a
    historical fact, and a function it names may have been deleted BY the very
    refactor the hotspot map motivated. Structure + vocab are what must hold.
    """
    seen_ids: set[str] = set()
    for row in rows:
        missing = [f for f in _REQUIRED if f not in row]
        if missing:
            raise LedgerError(f"finding {row.get('id', '?')!r}: missing required field(s) {missing}")
        fid = row["id"]
        if fid in seen_ids:
            raise LedgerError(f"duplicate finding id {fid!r}")
        seen_ids.add(fid)
        if row["subsystem"] not in SUBSYSTEMS:
            raise LedgerError(f"finding {fid!r}: unknown subsystem {row['subsystem']!r} (see SUBSYSTEMS)")
        if row["class"] not in _CLASSES:
            raise LedgerError(f"finding {fid!r}: unknown class {row['class']!r} (allowed: {sorted(_CLASSES)})")
        if row["discovery"] not in _SOURCES:
            raise LedgerError(f"finding {fid!r}: unknown discovery {row['discovery']!r} (allowed: {sorted(_SOURCES)})")
        if not isinstance(row["functions"], list) or not row["functions"]:
            raise LedgerError(f"finding {fid!r}: `functions` must be a non-empty list")


# ---------------------------------------------------------------------------
# Coverage enrichment — line coverage per subsystem, from the ratchet's JSON
# ---------------------------------------------------------------------------


def _function_spans(executor_path: str) -> dict[str, tuple[int, int]]:
    """Map each module-level function in executor.py to its (start, end) line span."""
    tree = ast.parse(open(executor_path, encoding="utf-8").read())
    spans: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans[node.name] = (node.lineno, node.end_lineno or node.lineno)
    return spans


def subsystem_line_coverage(executor_path: str, coverage_json_path: str) -> dict[str, tuple[int, int]]:
    """Per subsystem, (covered_lines, total_lines) over its functions' spans.

    Reads the branch-coverage ratchet's coverage.py JSON (executed/missing lines
    for executor.py) and intersects with each mapped function's AST line span.
    Returns {} if the coverage file is absent or has no executor.py entry — the
    report then omits the column with a caveat rather than guessing.
    """
    if not os.path.exists(coverage_json_path) or not os.path.exists(executor_path):
        return {}
    cov = json.load(open(coverage_json_path, encoding="utf-8"))
    files = cov.get("files", {})
    key = next((k for k in files if k.replace("\\", "/").endswith("tap_grid/gryphon/executor.py")), None)
    if key is None:
        return {}
    executed = set(files[key].get("executed_lines", []))
    missing = set(files[key].get("missing_lines", []))
    spans = _function_spans(executor_path)

    per: dict[str, tuple[int, int]] = {}
    for func, (start, end) in spans.items():
        sub = FUNCTION_SUBSYSTEM.get(func)
        if sub is None:
            continue
        rng = set(range(start, end + 1))
        covered = len(rng & executed)
        total = len(rng & (executed | missing))
        prev = per.get(sub, (0, 0))
        per[sub] = (prev[0] + covered, prev[1] + total)
    return per


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def report(ledger_path: str, executor_path: str = "", coverage_json_path: str = "") -> str:
    """Render the hotspot report: by subsystem (with coverage), function, tag, source."""
    rows = load(ledger_path)
    validate(rows)
    if not rows:
        return "no findings recorded yet."

    cov = subsystem_line_coverage(executor_path, coverage_json_path) if executor_path and coverage_json_path else {}
    by_sub = Counter(r["subsystem"] for r in rows)
    by_func = Counter(f for r in rows for f in r["functions"])
    by_tag = Counter(t for r in rows for t in r.get("tags", []))
    by_source = Counter(r["discovery"] for r in rows)
    by_class = Counter(r["class"] for r in rows)

    dates = sorted(r["date"] for r in rows)
    out = [
        f"Gryphon findings ledger — {len(rows)} finding(s), {dates[0]}..{dates[-1]}",
        "  by class: " + ", ".join(f"{c}={n}" for c, n in by_class.most_common()),
        "",
        "HOTSPOTS BY SUBSYSTEM  (read #find WITH line-cov: high-cov+high-find = refactor target;",
        "                        low-cov+low-find = blind spot, not clean)",
        f"  {'subsystem':22}  {'#find':>5}  {'line-cov':>9}  read",
    ]
    for sub, _ in sorted(by_sub.items(), key=lambda kv: (-kv[1], kv[0])):
        if sub in cov and cov[sub][1] > 0:
            covered, total = cov[sub]
            pct = 100.0 * covered / total
            cov_str = f"{pct:5.1f}%"
            read = "REFACTOR TARGET" if pct >= 70 else "hot but thin cov"
        else:
            cov_str = "   n/a"
            read = "(oracle/unmapped)" if sub == "oracle" else "no cov data"
        out.append(f"  {sub:22}  {by_sub[sub]:>5}  {cov_str:>9}  {read}")

    # Blind-spot surfacing: mapped subsystems with coverage but ZERO findings —
    # candidates for "under-looked" rather than "clean".
    if cov:
        silent = sorted(s for s in cov if by_sub.get(s, 0) == 0 and cov[s][1] > 0)
        if silent:
            out += ["", "  subsystems with coverage but NO findings (looked-at, currently clean — or under-probed):"]
            for s in silent:
                covered, total = cov[s]
                out.append(f"    {s:22}  line-cov {100.0 * covered / total:5.1f}%")

    out += ["", "HOTSPOTS BY FUNCTION", f"  {'function':32}  {'#find':>5}  subsystem"]
    for func, n in by_func.most_common():
        out.append(f"  {func:32}  {n:>5}  {FUNCTION_SUBSYSTEM.get(func, '(unmapped)')}")

    if by_tag:
        out += ["", "CROSS-CUTTING TAGS", *(f"  {t:22}  {n}" for t, n in by_tag.most_common())]
    out += ["", "BY DISCOVERY SOURCE", *(f"  {s:22}  {n}" for s, n in by_source.most_common())]
    return "\n".join(out)
