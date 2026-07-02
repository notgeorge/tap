"""github-deploy-health — per-workflow sparkline scoreboard.

Spec: plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
(req-github-core-repo-page-health).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from tap_plugin.github_core.models import GithubActionsRun, GithubWorkflow
from tap_plugin.github_core.panels._common import resolve_repo, status_pill

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

DEFAULT_WINDOW = 30


class DeployHealthPanelType:
    slug: ClassVar[str] = "github-deploy-health"
    label: ClassVar[str] = "GitHub Deploy Health"
    view: ClassVar[str] = "github_core/panels/deploy_health.html"
    css: ClassVar[list[str]] = ["github_core/css/panels.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {"window": DEFAULT_WINDOW}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        res = resolve_repo(panel, request)
        config = getattr(panel, "config", None) or {}
        try:
            window = int(config.get("window") or DEFAULT_WINDOW)
        except TypeError, ValueError:
            window = DEFAULT_WINDOW
        window = max(1, window)

        rows: list[dict[str, Any]] = []
        if res.repo is not None:
            workflows = list(GithubWorkflow.objects.filter(full_name=res.repo.full_name).order_by("name"))
            for wf in workflows:
                wf_runs = list(
                    GithubActionsRun.objects.filter(full_name=res.repo.full_name)
                    .filter(configuration__workflow_id=wf.workflow_id)
                    .order_by("-run_started_at")[:window]
                )
                boxes = [status_pill(r.status, r.conclusion) for r in reversed(wf_runs)]
                success_count = sum(1 for b in boxes if b["tone"] == "green")
                rows.append(
                    {
                        "workflow": wf,
                        "boxes": boxes,
                        "success_count": success_count,
                        "total": len(boxes),
                    }
                )
        return {"resolution": res, "rows": rows, "window": window}
