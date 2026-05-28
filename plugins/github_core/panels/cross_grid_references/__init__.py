"""github-cross-grid-references — outbound REFERENCES_RESOURCE edges grouped by target type.

The "mapping the tao" payoff panel. Spec:
plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
(req-github-core-repo-page-cross-grid).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, ClassVar

from django.apps import apps

from plugins.github_core.models import (
    GithubActionsJob,
    GithubActionsRun,
    GithubRepository,
    GithubWorkflow,
)
from plugins.github_core.panels._common import resolve_repo
from tap_grid.models import BaseModel, Edge

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


class CrossGridReferencesPanelType:
    slug: ClassVar[str] = "github-cross-grid-references"
    label: ClassVar[str] = "GitHub Cross-Grid References"
    view: ClassVar[str] = "github_core/panels/cross_grid_references.html"
    css: ClassVar[list[str]] = ["github_core/css/panels.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        res = resolve_repo(panel, request)
        groups: list[dict[str, Any]] = []
        total_edges = 0

        if res.repo is not None:
            source_ids = _source_entity_ids_for_repo(res.repo)
            edges = list(
                Edge.objects.filter(
                    edge_type="REFERENCES_RESOURCE",
                    from_entity_id__in=source_ids,
                )
            )
            total_edges = len(edges)

            target_ids = [str(e.to_entity_id) for e in edges]
            target_index = _build_target_index(target_ids)

            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for edge in edges:
                target = target_index.get(str(edge.to_entity_id))
                if target is None:
                    continue
                props = edge.properties or {}
                grouped[target.ENTITY_TYPE].append(
                    {
                        "target": target,
                        "target_display": _display_name(target),
                        "link_rule": props.get("link_rule", ""),
                        "matched_value": props.get("matched_value", ""),
                    }
                )

            for entity_type in sorted(grouped):
                groups.append(
                    {
                        "entity_type": entity_type,
                        "label": _humanize_entity_type(entity_type),
                        "count": len(grouped[entity_type]),
                        "rows": grouped[entity_type],
                    }
                )

        return {
            "resolution": res,
            "groups": groups,
            "total_edges": total_edges,
        }


def _source_entity_ids_for_repo(repo: GithubRepository) -> list[str]:
    ids: list[str] = [str(repo.entity_id)]
    for model in (GithubWorkflow, GithubActionsRun, GithubActionsJob):
        ids.extend(
            str(eid)
            for eid in model.objects.filter(full_name=repo.full_name).values_list(
                "entity_id", flat=True
            )
        )
    return ids


def _build_target_index(target_ids: list[str]) -> dict[str, BaseModel]:
    """Resolve target entity ids to their model instances across any BaseModel subclass."""
    index: dict[str, BaseModel] = {}
    remaining = set(target_ids)
    for model in apps.get_models():
        if not issubclass(model, BaseModel):
            continue
        if not remaining:
            break
        found = model.objects.filter(entity_id__in=list(remaining))
        for obj in found:
            index[str(obj.entity_id)] = obj
            remaining.discard(str(obj.entity_id))
    return index


def _display_name(obj: BaseModel) -> str:
    if hasattr(obj, "get_name"):
        try:
            return obj.get_name() or str(obj.entity_id)
        except Exception:
            pass
    return getattr(obj, "name", "") or str(obj.entity_id)


def _humanize_entity_type(slug: str) -> str:
    return slug.replace("_", " ").title()
