"""github-repo-hero — identity strip across the top of the repo landing page.

Spec: plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
(req-github-core-repo-page-hero).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from tap_plugin.github_core.panels._common import humanize_age, resolve_repo

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


class RepoHeroPanelType:
    slug: ClassVar[str] = "github-repo-hero"
    label: ClassVar[str] = "GitHub Repository Hero"
    view: ClassVar[str] = "github_core/panels/repo_hero.html"
    css: ClassVar[list[str]] = ["github_core/css/panels.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        res = resolve_repo(panel, request)
        repo = res.repo
        return {
            "resolution": res,
            "repo": repo,
            "last_collected_age": humanize_age(repo.entity.updated_at) if repo else None,
        }
