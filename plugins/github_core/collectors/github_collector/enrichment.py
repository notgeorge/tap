"""Grid-link enrichment phase — link manifest evaluator.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-grid-links). Runs as the second phase of GitHubCollector.run()
after the GitHub GRIFT batch lands. Reads `github_grid_link_manifest.json`,
walks each rule against landed github_core nodes for the configured repos,
queries the grid for exact-match candidates, and emits REFERENCES_RESOURCE
edges as a second GRIFT batch.

Derived link — not hotlink-backed. See req-github-core-grid-links-7.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from django.apps import apps

from tap_grid.models import BaseModel

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
class EnrichmentResult:
    edge_envelopes: list[dict[str, Any]] = field(default_factory=list)
    resolutions: list[LinkResolution] = field(default_factory=list)


def resolve_links(
    *,
    link_manifest: dict[str, Any],
    repos: list[str],
    edge_default_dimensions: dict[str, str],
) -> EnrichmentResult:
    """Evaluate every rule against landed github_core nodes for each repo."""
    result = EnrichmentResult()
    for rule in link_manifest.get("rules", []):
        try:
            source_model = _model_for(rule["source_entity_type"])
            target_model = _model_for(rule["target_entity_type"])
        except LookupError:
            logger.warning(
                "[a3f1] link rule %s: source or target model not installed; skipping",
                rule["name"],
            )
            continue

        source_qs = _source_queryset_for_repos(source_model, repos)
        for source_node in source_qs:
            values = _extract_values(source_node, rule["source_field_path"])
            for value in values:
                candidates = list(
                    target_model.objects.filter(**{rule["target_field"]: value})
                )
                if len(candidates) == 1:
                    target_node = candidates[0]
                    src_uuid = UUID(str(source_node.entity_id))
                    tgt_uuid = UUID(str(target_node.entity_id))
                    edge_uuid = edge_id(rule["edge_type"], src_uuid, tgt_uuid)
                    result.edge_envelopes.append(
                        edge_envelope(
                            entity_id=edge_uuid,
                            edge_type=rule["edge_type"],
                            source_id=src_uuid,
                            target_id=tgt_uuid,
                            dimensions=edge_default_dimensions,
                            properties={"link_rule": rule["name"], "matched_value": value},
                        )
                    )
                    result.resolutions.append(
                        LinkResolution(
                            rule_name=rule["name"],
                            source_entity_type=rule["source_entity_type"],
                            source_entity_id=src_uuid,
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
                            source_entity_id=UUID(str(source_node.entity_id)),
                            source_value=value,
                            candidate_count=len(candidates),
                            emitted_edge=False,
                        )
                    )
    return result


def _model_for(entity_type: str) -> type[BaseModel]:
    """Resolve an entity_type slug to its BaseModel subclass."""
    for model in apps.get_models():
        if issubclass(model, BaseModel) and getattr(model, "ENTITY_TYPE", None) == entity_type:
            return model
    raise LookupError(entity_type)


def _source_queryset_for_repos(model: type[BaseModel], repos: list[str]) -> Iterable[Any]:
    """Pull all source nodes scoped to the configured repos.

    Most github_core models carry `full_name` ("owner/repo"); for the rest
    (account-level) we just return everything the model has.
    """
    if hasattr(model, "full_name"):
        return model.objects.filter(full_name__in=repos)
    return model.objects.all()


def _extract_values(source_node: Any, field_path: str) -> list[str]:
    """Extract string values from a nested JSON path like 'configuration.refs.aws_regions[*]'.

    Supports dotted attribute/key access and `[*]` to flatten one list level.
    Returns deduplicated, non-empty strings.
    """
    path_tokens = field_path.replace("[*]", "").split(".")
    current: Any = source_node
    for token in path_tokens:
        if current is None:
            return []
        if hasattr(current, token):
            current = getattr(current, token)
        elif isinstance(current, dict):
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
