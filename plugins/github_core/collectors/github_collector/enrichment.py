"""Grid-link enrichment phase — link manifest evaluator.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-grid-links). Runs as the second phase of GitHubCollector.run()
after the GitHub GRIFT batch lands. Reads `github_grid_link_manifest.json`,
walks each rule against landed github_core nodes for the configured repos,
queries the grid via Gryphon for exact-match candidates, and emits
REFERENCES_RESOURCE edges as a second GRIFT batch.

Reads ride on Gryphon (per `feedback_gryphon_over_orm` + the
`req-grid-traversal-lang-regex` `=~` operator landed by the gryphon session
on 2026-05-28). The four read paths:

- source-node fetch  — `MATCH (n:<source_type>) WHERE n.data.full_name IN [...]`
                       OR labelless `MATCH (n) WHERE n.entity_type = $type`
                       when the source type has no full_name field
- exact-match query  — `MATCH (t:<target_type>) WHERE n.data.<field> = $value`
- near-match query   — `MATCH (t:<target_type>) WHERE n.data.<field> =~ $pattern
                                                  AND NOT n.data.<field> = $exact`
- target name lookup — comes from the envelope's spine `entity.name` (auto-
                       synced from `get_name()` per `req-grid-node-display`),
                       so no separate labelless lookup needed

Derived link — not hotlink-backed. See req-github-core-grid-links-7.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from .batch import edge_envelope
from .identity import edge_id

logger = logging.getLogger(__name__)


@dataclass
class LinkResolution:
    """Per-rule per-source-node resolution outcome (for warnings/info)."""

    rule_name: str
    source_entity_type: str
    source_entity_id: UUID
    source_value: str
    candidate_count: int
    emitted_edge: bool


@dataclass
class NearMatch:
    """A target row that matched a rule's `near_match_pattern` but not its exact value.

    Surfaces "looks like what you meant but isn't quite it" cases so the operator
    can investigate instead of silently missing the link.
    """

    rule_name: str
    target_entity_type: str
    target_value: str
    expected_value: str


@dataclass
class EnrichmentResult:
    edge_envelopes: list[dict[str, Any]] = field(default_factory=list)
    resolutions: list[LinkResolution] = field(default_factory=list)
    near_matches: list[NearMatch] = field(default_factory=list)


def resolve_links(
    *,
    link_manifest: dict[str, Any],
    repos: list[str],
    edge_default_dimensions: dict[str, str],
) -> EnrichmentResult:
    """Evaluate every rule against landed github_core nodes for each repo."""
    result = EnrichmentResult()
    for rule in link_manifest.get("rules", []):
        source_nodes = _fetch_source_nodes(rule["source_entity_type"], repos)
        near_match_pattern = rule.get("near_match_pattern")
        for source_node in source_nodes:
            source_data = source_node.get("data") or {}
            source_uuid = UUID(source_node["entity_id"])
            values = _values_for_source(source_data, rule)
            for value in values:
                candidates = _fetch_exact_candidates(
                    rule["target_entity_type"], rule["target_field"], value
                )
                if len(candidates) == 1:
                    target = candidates[0]
                    tgt_uuid = UUID(target["entity_id"])
                    edge_uuid = edge_id(rule["edge_type"], source_uuid, tgt_uuid)
                    result.edge_envelopes.append(
                        edge_envelope(
                            entity_id=edge_uuid,
                            edge_type=rule["edge_type"],
                            source_id=source_uuid,
                            target_id=tgt_uuid,
                            dimensions=edge_default_dimensions,
                            properties={"link_rule": rule["name"], "matched_value": value},
                        )
                    )
                    result.resolutions.append(
                        LinkResolution(
                            rule_name=rule["name"],
                            source_entity_type=rule["source_entity_type"],
                            source_entity_id=source_uuid,
                            source_value=value,
                            candidate_count=1,
                            emitted_edge=True,
                        )
                    )
                else:
                    result.resolutions.append(
                        LinkResolution(
                            rule_name=rule["name"],
                            source_entity_type=rule["source_entity_type"],
                            source_entity_id=source_uuid,
                            source_value=value,
                            candidate_count=len(candidates),
                            emitted_edge=False,
                        )
                    )
                    # Near-match surfacing: zero exact matches + a target row
                    # matching the rule's near_match_pattern → warn per row,
                    # no edge. Pattern is a Postgres POSIX regex; `(?i)` prefix
                    # opts into case-insensitive matching.
                    if len(candidates) == 0 and near_match_pattern:
                        near_rows = _fetch_near_matches(
                            rule["target_entity_type"],
                            rule["target_field"],
                            value,
                            near_match_pattern,
                        )
                        for near in near_rows:
                            near_data = near.get("data") or {}
                            result.near_matches.append(
                                NearMatch(
                                    rule_name=rule["name"],
                                    target_entity_type=rule["target_entity_type"],
                                    target_value=str(near_data.get(rule["target_field"], "")),
                                    expected_value=value,
                                )
                            )
    return result


# ---------------------------------------------------------------------------
# Gryphon read helpers
# ---------------------------------------------------------------------------


def _fetch_source_nodes(
    source_entity_type: str, repos: list[str]
) -> list[dict[str, Any]]:
    """Return source-node envelopes for the configured repos.

    Most github_core models carry a `full_name` field ("owner/repo"); we IN-
    list against that. Models without `full_name` (e.g. `github_account`) fall
    back to a type-scoped scan — every account on the grid for that type.
    """
    if not repos:
        return []
    repo_params, repo_in = _in_list_params(repos, prefix="repo")
    # First try with full_name filter; if it errors (field absent for the
    # type), retry without. The cheaper alternative would be to know per
    # type whether full_name is a field, but the link manifest is plugin-
    # generic and shouldn't carry that knowledge.
    try:
        query = (
            f"MATCH (n:{source_entity_type}) "
            f"WHERE n.data.full_name IN [{repo_in}] "
            "RETURN n"
        )
        return _gryphon_nodes(query, inputs=repo_params)
    except Exception:  # noqa: BLE001 - bare match scope, see comment above
        query = f"MATCH (n:{source_entity_type}) RETURN n"
        return _gryphon_nodes(query, inputs={})


def _fetch_exact_candidates(
    target_entity_type: str, target_field: str, value: str
) -> list[dict[str, Any]]:
    """Return target-node envelopes whose `target_field` equals `value` exactly."""
    query = (
        f"MATCH (n:{target_entity_type}) "
        f"WHERE n.data.{target_field} = $value "
        "RETURN n"
    )
    return _gryphon_nodes(query, inputs={"value": value})


def _fetch_near_matches(
    target_entity_type: str,
    target_field: str,
    exact_value: str,
    pattern: str,
) -> list[dict[str, Any]]:
    """Return target-node envelopes whose `target_field` matches the regex pattern
    but isn't the exact value.

    Uses Gryphon's `=~` (search-semantics Postgres regex). Pattern is passed
    through verbatim — `(?i)` prefix in the manifest opts into case-insensitive
    matching.
    """
    query = (
        f"MATCH (n:{target_entity_type}) "
        f"WHERE n.data.{target_field} =~ $pattern "
        f"AND NOT n.data.{target_field} = $exact "
        "RETURN n"
    )
    return _gryphon_nodes(
        query, inputs={"pattern": pattern, "exact": exact_value}
    )


def _gryphon_nodes(query: str, *, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Run a Gryphon search and return the `nodes` envelopes from the result."""
    # Local imports keep tap_grid out of the import-time graph for collector
    # tests that don't need it.
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    input_schema = _input_schema_for(inputs)
    search = Search(
        search_type="gryphon",
        root="node",
        name="github_core-enrichment-resolver",
        input_schema=input_schema,
        definition={"query": [query]},
        default_limit=500,
        max_limit=2000,
    )
    result = execute_search(search, inputs=inputs, layer="extended")
    envelope = result.get("results", result)
    return list(envelope.get("nodes", []) or [])


def _input_schema_for(inputs: dict[str, Any]) -> dict[str, Any]:
    """Minimal JSON Schema for the input dict (everything is a string in v0)."""
    return {
        "type": "object",
        "properties": {k: {"type": "string"} for k in inputs},
        "required": list(inputs.keys()),
    }


def _in_list_params(
    values: Iterable[str], *, prefix: str
) -> tuple[dict[str, Any], str]:
    """Build (params_dict, in_list_text) for a Gryphon `IN [$p0, $p1, ...]` clause."""
    params: dict[str, Any] = {}
    placeholders: list[str] = []
    for i, v in enumerate(values):
        name = f"{prefix}{i}"
        params[name] = v
        placeholders.append(f"${name}")
    return params, ", ".join(placeholders)


# ---------------------------------------------------------------------------
# Source-value extraction
# ---------------------------------------------------------------------------


def _values_for_source(source_data: dict[str, Any], rule: dict[str, Any]) -> list[str]:
    """Return the source-side match values for one rule + one source node.

    Two flavors per `req-github-core-grid-links`-aligned manifest shape:
      - `source_field_path` — extract from the data dict's nested JSON.
      - `source_constant`   — literal value applied to every source node
                              (used for structural rules like 'every repo
                              federates with this canonical URL').
    """
    if "source_constant" in rule:
        return [rule["source_constant"]]
    return _extract_values(source_data, rule["source_field_path"])


def _extract_values(source_data: dict[str, Any], field_path: str) -> list[str]:
    """Extract string values from a nested JSON path like 'configuration.refs.aws_regions[*]'.

    Supports dotted key access and `[*]` to flatten one list level.
    Returns deduplicated, non-empty strings.
    """
    path_tokens = field_path.replace("[*]", "").split(".")
    current: Any = source_data
    for token in path_tokens:
        if current is None:
            return []
        if isinstance(current, dict):
            current = current.get(token)
        else:
            return []
    if current is None:
        return []
    values = current if isinstance(current, list) else [current]
    out: list[str] = []
    for v in values:
        if isinstance(v, str) and v and v not in out:
            out.append(v)
    return out


# Kept as a stable JSON-blob accessor in case future rules want richer source
# extraction (e.g. struct payloads). Not used by the v0 rules.
def _normalize_jsonable(value: Any) -> Any:  # pragma: no cover - utility
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value
