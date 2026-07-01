"""github-history-strip — compact history summary for the repo's workflows.

Spec: plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
(req-github-core-repo-page-history).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from tap_plugin.github_core.models import GithubWorkflow
from tap_plugin.github_core.panels._common import humanize_age, resolve_repo

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


class HistoryStripPanelType:
    slug: ClassVar[str] = "github-history-strip"
    label: ClassVar[str] = "GitHub History Strip"
    view: ClassVar[str] = "github_core/panels/history_strip.html"
    css: ClassVar[list[str]] = ["github_core/css/panels.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        res = resolve_repo(panel, request)
        total_changes = 0
        latest_change: dict[str, Any] | None = None

        if res.repo is not None:
            history_qs = GithubWorkflow.history.filter(full_name=res.repo.full_name)
            total_changes = history_qs.count()
            latest = history_qs.order_by("-history_date").first()
            if latest is not None:
                latest_change = {
                    "workflow_name": latest.name or latest.path or "—",
                    "history_date": latest.history_date,
                    "age": humanize_age(latest.history_date),
                    "history_type": latest.history_type,  # "+" created, "~" updated, "-" deleted
                    "html_url": latest.html_url,
                }

        return {
            "resolution": res,
            "total_changes": total_changes,
            "latest_change": latest_change,
        }
