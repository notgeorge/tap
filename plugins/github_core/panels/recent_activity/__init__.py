"""github-recent-activity — chronological list of recent workflow runs.

Spec: plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
(req-github-core-repo-page-activity).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from plugins.github_core.models import GithubActionsRun, GithubWorkflow
from plugins.github_core.panels._common import humanize_age, resolve_repo, status_pill

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

DEFAULT_LIMIT = 10
MAX_LIMIT = 100


class RecentActivityPanelType:
    slug: ClassVar[str] = "github-recent-activity"
    label: ClassVar[str] = "GitHub Recent Activity"
    view: ClassVar[str] = "github_core/panels/recent_activity.html"
    css: ClassVar[list[str]] = ["github_core/css/panels.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {"limit": DEFAULT_LIMIT}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        res = resolve_repo(panel, request)
        config = getattr(panel, "config", None) or {}
        try:
            limit = int(config.get("limit") or DEFAULT_LIMIT)
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))

        rows: list[dict[str, Any]] = []
        if res.repo is not None:
            runs = list(
                GithubActionsRun.objects.filter(full_name=res.repo.full_name)
                .order_by("-run_started_at")[:limit]
            )
            # Join workflows once — N+1 avoidance for the demo dataset (small).
            workflow_ids = {r.configuration.get("workflow_id") for r in runs if r.configuration}
            workflows = {
                w.workflow_id: w
                for w in GithubWorkflow.objects.filter(
                    full_name=res.repo.full_name,
                    workflow_id__in=[wid for wid in workflow_ids if wid],
                )
            }
            for r in runs:
                wf_id = (r.configuration or {}).get("workflow_id")
                workflow = workflows.get(wf_id)
                rows.append(
                    {
                        "run": r,
                        "workflow_name": (workflow.name if workflow else "")
                        or (workflow.path if workflow else "")
                        or "—",
                        "pill": status_pill(r.status, r.conclusion),
                        "short_sha": (r.head_sha or "")[:8],
                        "age": humanize_age(r.run_started_at),
                    }
                )
        return {"resolution": res, "rows": rows, "limit": limit}
