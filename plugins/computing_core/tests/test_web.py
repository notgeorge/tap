"""Domain-specific tests for the web-native Computing Core types.

`web_host` and `web_document` (req-computing-core-models-6) plus the
`HOSTED_BY` / `FETCHES` edges. These cover service-layer creation, required
fields, display projection, the `tap.web` web-native marker
(req-computing-core-web-marker), and that the edges connect.
"""

import pytest

import plugins.computing_core.models as computing  # noqa: F401 — trigger model registration
from tap_grid.models import Entity
from tap_grid.registry import get_model_class
from tap_grid.services import create_edge, create_node


def _create(type_slug: str, payload: dict):
    """Create a node via the service layer and return the typed domain object."""
    result = create_node(type_slug, payload)
    assert result.success, f"create_node failed: {result.errors}"
    entity = Entity.objects.get(pk=result.entity_id)
    model_cls = get_model_class(type_slug)
    return model_cls.objects.get(entity=entity)


@pytest.mark.django_db
class TestWebHost:
    def test_create_and_display(self):
        node = _create("web_host", {"name": "CISA", "hostname": "www.cisa.gov"})
        node.entity.refresh_from_db()
        assert node.hostname == "www.cisa.gov"
        assert node.entity.name == "CISA"

    def test_name_falls_back_to_hostname(self):
        node = _create("web_host", {"hostname": "www.cisa.gov"})
        node.entity.refresh_from_db()
        assert node.entity.name == "www.cisa.gov"

    def test_hostname_required(self):
        result = create_node("web_host", {"name": "no host"})
        assert not result.success

    def test_web_native_marker(self):
        node = _create("web_host", {"hostname": "www.cisa.gov"})
        assert node.entity.dimensions.get("tap.computing") == "network"
        assert node.entity.dimensions.get("tap.web") == "native"


@pytest.mark.django_db
class TestWebDocument:
    def test_create_with_metadata(self):
        node = _create(
            "web_document",
            {
                "name": "CISA KEV catalog",
                "url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                "content_type": "application/json",
                "version": "2026.05.29",
                "retrieved_at": "2026-05-29T12:00:00Z",
            },
        )
        assert node.content_type == "application/json"
        assert node.version == "2026.05.29"
        assert node.retrieved_at is not None

    def test_url_required(self):
        result = create_node("web_document", {"name": "no url"})
        assert not result.success

    def test_web_native_marker(self):
        node = _create("web_document", {"url": "https://example.com/doc.json"})
        assert node.entity.dimensions.get("tap.computing") == "storage"
        assert node.entity.dimensions.get("tap.web") == "native"


@pytest.mark.django_db
class TestWebEdges:
    def test_hosted_by_connects_document_to_host(self):
        host = _create("web_host", {"hostname": "www.cisa.gov"})
        doc = _create("web_document", {"url": "https://www.cisa.gov/feed.json"})
        edge = create_edge(doc.entity, host.entity, "HOSTED_BY")
        assert edge.edge_type == "HOSTED_BY"

    def test_fetches_targets_a_web_document(self):
        doc = _create("web_document", {"url": "https://www.cisa.gov/feed.json"})
        # Source is wildcard; a file node stands in for an arbitrary fetcher here.
        fetcher = _create("file", {"file_path": "/tmp/fetcher"})
        edge = create_edge(fetcher.entity, doc.entity, "FETCHES")
        assert edge.edge_type == "FETCHES"
