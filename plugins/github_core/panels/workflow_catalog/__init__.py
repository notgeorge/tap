"""github-workflow-catalog — list of workflows with click-to-expand parsed detail.

Spec: plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
(req-github-core-repo-page-catalog).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from plugins.github_core.models import GithubActionsRun, GithubWorkflow
from plugins.github_core.panels._common import humanize_age, resolve_repo, status_pill

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


class WorkflowCatalogPanelType:
    slug: ClassVar[str] = "github-workflow-catalog"
    label: ClassVar[str] = "GitHub Workflow Catalog"
    view: ClassVar[str] = "github_core/panels/workflow_catalog.html"
    css: ClassVar[list[str]] = ["github_core/css/panels.css"]
    js: ClassVar[list[str]] = ["github_core/js/workflow_catalog.js"]
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        res = resolve_repo(panel, request)
        rows: list[dict[str, Any]] = []
        default_expanded_index: int | None = None
        if res.repo is not None:
            workflows = list(
                GithubWorkflow.objects.filter(full_name=res.repo.full_name).order_by("name")
            )
            # Pick the workflow with the most recent run for default expansion.
            most_recent_workflow_id: int | None = None
            most_recent_run = (
                GithubActionsRun.objects.filter(full_name=res.repo.full_name)
                .order_by("-run_started_at")
                .first()
            )
            if most_recent_run is not None:
                most_recent_workflow_id = (most_recent_run.configuration or {}).get("workflow_id")

            for idx, wf in enumerate(workflows):
                last_run = (
                    GithubActionsRun.objects.filter(full_name=res.repo.full_name)
                    .filter(configuration__workflow_id=wf.workflow_id)
                    .order_by("-run_started_at")
                    .first()
                )
                cfg = wf.configuration or {}
                jobs_summary = []
                for job in cfg.get("jobs", []) or []:
                    jobs_summary.append(
                        {
                            "id": job.get("id"),
                            "name": job.get("name"),
                            "runs_on": job.get("runs_on"),
                            "needs": job.get("needs") or [],
                            "uses": job.get("uses") or "",
                        }
                    )
                raw_yaml = cfg.get("raw_yaml") or ""
                rows.append(
                    {
                        "workflow": wf,
                        "last_run": last_run,
                        "last_run_pill": status_pill(
                            last_run.status if last_run else "",
                            last_run.conclusion if last_run else "",
                        )
                        if last_run
                        else None,
                        "last_run_age": humanize_age(last_run.run_started_at)
                        if last_run
                        else "—",
                        "triggers": cfg.get("triggers") or [],
                        "permissions": cfg.get("permissions") or {},
                        "jobs": jobs_summary,
                        "raw_yaml": raw_yaml,
                        "raw_yaml_bytes": len(raw_yaml.encode("utf-8")) if raw_yaml else 0,
                    }
                )
                if most_recent_workflow_id and wf.workflow_id == most_recent_workflow_id:
                    default_expanded_index = idx
        return {
            "resolution": res,
            "rows": rows,
            "default_expanded_index": default_expanded_index,
        }
