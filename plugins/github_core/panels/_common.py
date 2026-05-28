"""Shared helpers for github_core landing-page panels.

Spec: plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
(req-github-core-repo-page-resolution).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from plugins.github_core.models import GithubRepository

DEFAULT_REPO_VAR = "repository_entity_id"


@dataclass
class RepoResolution:
    """Outcome of resolving the page's `repository_entity_id` page variable."""

    repo: GithubRepository | None
    source: str  # "explicit" | "fallback" | "not_found" | "empty_grid"
    requested_entity_id: str  # raw value the operator supplied, "" if absent


def resolve_repo(panel: Any, request: Any) -> RepoResolution:
    """Resolve the `repository_entity_id` page variable to a github_repository node.

    Behavior (req-github-core-repo-page-resolution):
      - explicit: variable supplied + matches a row → return that repo
      - fallback: variable absent → latest by updated_at; empty grid → empty_grid
      - not_found: variable supplied + no matching row → no repo, source records the id
    """
    var_name = (
        (getattr(panel, "config", None) or {}).get("repo_entity_id_var") or DEFAULT_REPO_VAR
    )
    requested = (request.GET.get(var_name) or "").strip() if request else ""

    if requested:
        try:
            repo = GithubRepository.objects.filter(entity_id=requested).first()
        except (ValueError, GithubRepository.DoesNotExist):
            repo = None
        if repo is None:
            return RepoResolution(repo=None, source="not_found", requested_entity_id=requested)
        return RepoResolution(repo=repo, source="explicit", requested_entity_id=requested)

    repo = GithubRepository.objects.order_by("-entity__updated_at").first()
    if repo is None:
        return RepoResolution(repo=None, source="empty_grid", requested_entity_id="")
    return RepoResolution(repo=repo, source="fallback", requested_entity_id="")


# Status pill vocabulary (req-github-core-repo-page-activity-3).
# Maps GitHub's (status, conclusion) into a stable visual vocabulary the
# templates use directly.
STATUS_PILL_VOCABULARY = {
    "success": {"label": "success", "tone": "green"},
    "failure": {"label": "failure", "tone": "red"},
    "cancelled": {"label": "cancelled", "tone": "grey"},
    "skipped": {"label": "skipped", "tone": "grey"},
    "neutral": {"label": "neutral", "tone": "grey"},
    "timed_out": {"label": "timed out", "tone": "red"},
    "action_required": {"label": "action required", "tone": "yellow"},
    "stale": {"label": "stale", "tone": "grey"},
    "in_progress": {"label": "in progress", "tone": "yellow"},
    "queued": {"label": "queued", "tone": "yellow"},
    "waiting": {"label": "waiting", "tone": "yellow"},
    "pending": {"label": "pending", "tone": "yellow"},
    "requested": {"label": "requested", "tone": "yellow"},
}


def status_pill(status: str, conclusion: str) -> dict[str, str]:
    """Return `{label, tone}` for the (status, conclusion) pair.

    When the run is completed, conclusion drives the pill; otherwise status does.
    Unknown values map to a neutral grey "unknown" pill rather than erroring.
    """
    key = (conclusion or status or "").lower()
    pill = STATUS_PILL_VOCABULARY.get(key)
    if pill is not None:
        return pill
    return {"label": key or "unknown", "tone": "grey"}


def humanize_age(when: Any) -> str:
    """Coarse relative-duration label for a datetime; '—' when None."""
    if when is None:
        return "—"
    try:
        delta = timezone.now() - when
    except TypeError:
        return "—"
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    days = seconds // 86400
    if days < 14:
        return f"{days}d ago"
    if days < 60:
        return f"{days // 7}w ago"
    return f"{days // 30}mo ago"
