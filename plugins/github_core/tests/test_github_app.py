"""Tests for the github_app type, ENABLED_ON edge, and Dependabot detection.

Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-app)
"""

import pytest

import tap_plugin.github_core.models as github  # noqa: F401 — trigger model registration
from tap_plugin.github_core.collectors.github_collector.collector import _SYNTHETIC_APP_BY_PATH_PREFIX
from tap_plugin.github_core.collectors.github_collector.identity import github_app_id, workflow_id
from tap_grid.models import Entity
from tap_grid.registry import get_model_class
from tap_grid.services import create_edge, create_node


def _create(type_slug: str, payload: dict):
    result = create_node(type_slug, payload)
    assert result.success, f"create_node failed: {result.errors}"
    entity = Entity.objects.get(pk=result.entity_id)
    return get_model_class(type_slug).objects.get(entity=entity)


@pytest.mark.django_db
class TestGithubApp:
    def test_create_and_display(self):
        app = _create("github_app", {"slug": "dependabot", "name": "Dependabot"})
        app.entity.refresh_from_db()
        assert app.slug == "dependabot"
        assert app.entity.name == "Dependabot"
        assert app.entity.dimensions.get("github.surface") == "apps"

    def test_name_falls_back_to_slug(self):
        app = _create("github_app", {"slug": "dependabot"})
        app.entity.refresh_from_db()
        assert app.entity.name == "dependabot"

    def test_slug_required(self):
        result = create_node("github_app", {"name": "no slug"})
        assert not result.success


@pytest.mark.django_db
class TestEnabledOnEdge:
    def test_app_enabled_on_repository(self):
        app = _create("github_app", {"slug": "dependabot", "name": "Dependabot"})
        repo = _create("github_repository", {"full_name": "notgeorge/samsite"})
        edge = create_edge(app.entity, repo.entity, "ENABLED_ON")
        assert edge.edge_type == "ENABLED_ON"


class TestGithubAppIdentity:
    def test_deterministic_and_distinct_from_workflow(self):
        assert github_app_id("dependabot") == github_app_id("dependabot")
        # Same string, different entity type → different id.
        assert github_app_id("dependabot") != workflow_id("dependabot", 1)


class TestDependabotDetection:
    def test_synthetic_dependabot_path_recognized(self):
        path = "dynamic/dependabot/dependabot-updates"
        match = next((m for p, m in _SYNTHETIC_APP_BY_PATH_PREFIX.items() if path.startswith(p)), None)
        assert match is not None
        assert match["slug"] == "dependabot"

    def test_real_workflow_path_not_matched(self):
        path = ".github/workflows/deploy-with-opa.yml"
        match = next((m for p, m in _SYNTHETIC_APP_BY_PATH_PREFIX.items() if path.startswith(p)), None)
        assert match is None
