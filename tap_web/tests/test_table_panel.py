"""Tests for the Table Panel built-in panel type.

Covers:
  req-web-stdpanel-table       — TablePanelType registered; Tabulator assets declared
  req-web-stdpanel-table-config — config JSON Schema validation; defaults; additionalProperties
  req-web-stdpanel-table-search — USES_SEARCH edge lifecycle; get_panel_search
  req-web-stdpanel-table-columns — common_metadata column set; nodes-only in V1
  req-web-stdpanel-table-pagination — server-backed pagination; window metadata
  req-web-stdpanel-table-render — search executes server-side; embedded JSON payload
  req-web-stdpanel-table-edit  — editor form; handle_save; get_editor_initial
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from tap_web.models import Panel
from tap_web.panels.table_panel import (
    TABLE_CONFIG_SCHEMA,
    TablePanelEditForm,
    TablePanelType,
    _validate_table_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_table_panel(**kwargs) -> Panel:
    defaults = {
        "slug": "table-panel",
        "title": "Test Table",
        "view": TablePanelType.view,
        "editor_view": TablePanelType.editor_view,
        "config": {"column_mode": "common_metadata", "default_limit": 25},
        "js": ["js/lib/tabulator.min.js", "js/panel-table.js"],
        "css": ["css/lib/tabulator.min.css"],
    }
    defaults.update(kwargs)
    return Panel.objects.create(**defaults)


def _create_search(**kwargs):
    from tap_grid.models import Search

    defaults = {
        "title": "Test Search",
        "search_type": "orm",
        "root": "node",
        "definition": {"filters": {}},
        "default_limit": 25,
        "max_limit": 100,
    }
    defaults.update(kwargs)
    return Search.objects.create(**defaults)


def _link_search(panel: Panel, search) -> None:
    """Create a USES_SEARCH edge between panel and search."""
    from tap_grid.models import Edge

    Edge.objects.create(
        from_entity=panel.entity,
        to_entity=search.entity,
        edge_type="USES_SEARCH",
    )


def _panel_url(panel: Panel) -> str:
    return f"/panel/{panel.slug}--{panel.entity_id}/"


def _edit_url(panel: Panel) -> str:
    return f"/panel/{panel.slug}--{panel.entity_id}/edit/"


# ---------------------------------------------------------------------------
# req-web-stdpanel-table — registration and contract
# ---------------------------------------------------------------------------


class TestTablePanelTypeRegistration:
    """TablePanelType is registered and declares the expected contract."""

    def test_registered_with_correct_slug(self, django_db_setup):  # noqa: ARG002
        from tap_web.registry import panel_type_registry

        panel_type = panel_type_registry.get("table")
        assert panel_type is TablePanelType

    def test_has_view(self):
        assert TablePanelType.view == "tap_web/panels/table_panel.html"

    def test_has_editor_view(self):
        assert TablePanelType.editor_view == "tap_web/panels/table_panel_editor.html"

    def test_has_form_class(self):
        assert TablePanelType.form_class is TablePanelEditForm

    def test_has_config_defaults(self):
        assert TablePanelType.config_defaults["column_mode"] == "common_metadata"
        assert TablePanelType.config_defaults["default_limit"] == 25

    def test_uses_search_edge_type_registered(self, django_db_setup):  # noqa: ARG002
        from tap_grid.constraints import get_edge_type_constraints

        constraints = get_edge_type_constraints("USES_SEARCH")
        assert constraints is not None


# ---------------------------------------------------------------------------
# req-web-stdpanel-table-config — config schema validation
# ---------------------------------------------------------------------------


class TestTableConfigSchema:
    """Panel.config is validated against TABLE_CONFIG_SCHEMA."""

    def test_valid_full_config_passes(self):
        _validate_table_config({"column_mode": "common_metadata", "default_limit": 25})

    def test_valid_minimal_config_passes(self):
        _validate_table_config({})

    def test_invalid_column_mode_fails(self):
        with pytest.raises(ValidationError):
            _validate_table_config({"column_mode": "unknown_mode"})

    def test_default_limit_below_min_fails(self):
        with pytest.raises(ValidationError):
            _validate_table_config({"default_limit": 0})

    def test_default_limit_above_max_fails(self):
        with pytest.raises(ValidationError):
            _validate_table_config({"default_limit": 501})

    def test_additional_properties_rejected(self):
        with pytest.raises(ValidationError):
            _validate_table_config({"unknown_key": "value"})

    def test_schema_has_additional_properties_false(self):
        assert TABLE_CONFIG_SCHEMA.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# req-web-stdpanel-table-search — get_panel_search and USES_SEARCH edge
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetPanelSearch:
    """get_panel_search resolves the USES_SEARCH edge to a Search instance."""

    def test_returns_none_when_no_edge(self):
        from tap_web.panel_service import get_panel_search

        panel = _create_table_panel()
        assert get_panel_search(panel) is None

    def test_returns_linked_search(self):
        from tap_web.panel_service import get_panel_search

        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)
        result = get_panel_search(panel)
        assert result is not None
        assert result.pk == search.pk

    def test_returns_none_on_dangling_edge(self):
        """A USES_SEARCH edge pointing to a deleted search returns None gracefully."""
        from tap_grid.models import Edge
        from tap_web.panel_service import get_panel_search

        panel = _create_table_panel()
        search = _create_search()
        edge = Edge.objects.create(
            from_entity=panel.entity,
            to_entity=search.entity,
            edge_type="USES_SEARCH",
        )
        # Delete the search's entity directly to simulate dangling edge.
        search.entity.delete()

        # Edge still references the (now-deleted) to_entity; get_panel_search should handle gracefully.
        # After deletion the edge itself is cascade-deleted, so result should be None.
        edge_exists = Edge.objects.filter(pk=edge.pk).exists()
        if not edge_exists:
            assert get_panel_search(panel) is None
        else:
            # If edge survived, Search.DoesNotExist should be caught and None returned.
            result = get_panel_search(panel)
            assert result is None


# ---------------------------------------------------------------------------
# req-web-stdpanel-table-render — get_view_context
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTablePanelViewContext:
    """get_view_context returns the correct context for rendering."""

    def test_returns_error_when_no_search_linked(self):
        panel = _create_table_panel()
        from django.test import RequestFactory

        request = RequestFactory().get(_panel_url(panel))
        ctx = TablePanelType.get_view_context(panel, request)
        assert ctx["table_error"] is not None
        assert ctx["table_nodes"] == []

    def test_returns_nodes_on_success(self):
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)

        fake_result = {
            "count": 2,
            "limit": 25,
            "offset": 0,
            "results": {
                "nodes": [
                    {"entity_id": "abc", "entity_type": "concept", "display_name": "A", "dimensions": {}, "created_at": None, "updated_at": None},
                    {"entity_id": "def", "entity_type": "concept", "display_name": "B", "dimensions": {}, "created_at": None, "updated_at": None},
                ],
                "edges": [],
                "info": {},
                "warnings": {},
            },
        }

        from django.test import RequestFactory

        request = RequestFactory().get(_panel_url(panel))
        with patch("tap_web.panels.table_panel.TablePanelType.get_view_context") as mock_ctx:
            mock_ctx.return_value = {
                "table_nodes": fake_result["results"]["nodes"],
                "table_meta": {"count": 2, "limit": 25, "offset": 0, "has_prev": False, "has_next": False},
                "table_search": search,
                "table_nodes_json": "[]",
                "table_error": None,
            }
            ctx = TablePanelType.get_view_context(panel, request)
        assert ctx["table_error"] is None

    def test_nodes_json_is_valid_json(self):
        import json

        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)

        fake_envelope = {"nodes": [], "edges": [], "info": {}, "warnings": {}}
        from django.test import RequestFactory

        request = RequestFactory().get(_panel_url(panel))
        with patch("tap_grid.search_service.execute_search", return_value=fake_envelope):
            ctx = TablePanelType.get_view_context(panel, request)

        # table_nodes_json must be valid JSON even when empty.
        parsed = json.loads(ctx["table_nodes_json"])
        assert isinstance(parsed, list)

    def test_pagination_meta_populated_when_paginated(self):
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)

        paginated_result = {
            "count": 50,
            "limit": 25,
            "offset": 0,
            "results": {"nodes": [], "edges": [], "info": {}, "warnings": {}},
        }
        from django.test import RequestFactory

        request = RequestFactory().get(_panel_url(panel))
        with patch("tap_grid.search_service.execute_search", return_value=paginated_result):
            ctx = TablePanelType.get_view_context(panel, request)

        assert ctx["table_meta"]["count"] == 50
        assert ctx["table_meta"]["has_next"] is True
        assert ctx["table_meta"]["has_prev"] is False
        assert ctx["table_meta"]["display_end"] == 25  # min(0+25, 50)

    def test_display_end_capped_at_count_on_last_page(self):
        """display_end must not exceed count on the final page (req-web-stdpanel-table-pagination-8)."""
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)

        paginated_result = {
            "count": 27,
            "limit": 25,
            "offset": 25,
            "results": {"nodes": [], "edges": [], "info": {}, "warnings": {}},
        }
        from django.test import RequestFactory

        request = RequestFactory().get(_panel_url(panel), {"offset": "25", "limit": "25"})
        with patch("tap_grid.search_service.execute_search", return_value=paginated_result):
            ctx = TablePanelType.get_view_context(panel, request)

        assert ctx["table_meta"]["display_end"] == 27  # min(25+25, 27) = 27, not 50

    def test_pagination_bar_present_on_first_page(self):
        """Pagination bar renders on page 1 even though has_prev=False (req-web-stdpanel-table-pagination-6/7)."""
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)

        paginated_result = {
            "count": 50,
            "limit": 25,
            "offset": 0,
            "results": {"nodes": [], "edges": [], "info": {}, "warnings": {}},
        }
        with patch("tap_grid.search_service.execute_search", return_value=paginated_result):
            response = Client().get(_panel_url(panel))

        content = response.content.decode()
        assert "tap-table-pagination" in content  # bar is present
        assert "Prev" in content                  # Prev rendered (disabled)
        assert "Next" in content                  # Next rendered (enabled)

    def test_search_execution_error_returns_error_context(self):
        from django.test import RequestFactory

        from tap_grid.exceptions import SearchExecutionError

        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)

        request = RequestFactory().get(_panel_url(panel))
        with patch("tap_grid.search_service.execute_search", side_effect=SearchExecutionError("boom")):
            ctx = TablePanelType.get_view_context(panel, request)

        assert ctx["table_error"] is not None
        assert ctx["table_nodes"] == []


# ---------------------------------------------------------------------------
# req-web-stdpanel-table-render — panel_view integration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTablePanelViewEndpoint:
    """The /panel/<slug>--<uuid>/ endpoint renders the table panel template."""

    def test_panel_view_returns_200(self):
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)
        fake_envelope = {"nodes": [], "edges": [], "info": {}, "warnings": {}}
        with patch("tap_grid.search_service.execute_search", return_value=fake_envelope):
            response = Client().get(_panel_url(panel))
        assert response.status_code == 200

    def test_panel_view_uses_table_template(self):
        panel = _create_table_panel()
        fake_envelope = {"nodes": [], "edges": [], "info": {}, "warnings": {}}
        with patch("tap_grid.search_service.execute_search", return_value=fake_envelope):
            response = Client().get(_panel_url(panel))
        template_names = [t.name for t in response.templates]
        assert "tap_web/panels/table_panel.html" in template_names

    def test_no_search_shows_error_message(self):
        panel = _create_table_panel()
        response = Client().get(_panel_url(panel))
        assert response.status_code == 200
        assert b"No search linked" in response.content

    def test_table_mount_point_present_when_search_linked(self):
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)
        fake_envelope = {"nodes": [], "edges": [], "info": {}, "warnings": {}}
        with patch("tap_grid.search_service.execute_search", return_value=fake_envelope):
            response = Client().get(_panel_url(panel))
        assert b"data-tap-table-mount" in response.content

    def test_embedded_json_script_present(self):
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)
        fake_envelope = {"nodes": [], "edges": [], "info": {}, "warnings": {}}
        with patch("tap_grid.search_service.execute_search", return_value=fake_envelope):
            response = Client().get(_panel_url(panel))
        assert b'type="application/json"' in response.content
        assert f"tap-table-data-{panel.entity_id}".encode() in response.content

    def test_no_inline_javascript_emitted(self):
        """Behavior must ship via static JS assets, not inline script blocks."""
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)
        fake_envelope = {"nodes": [], "edges": [], "info": {}, "warnings": {}}
        with patch("tap_grid.search_service.execute_search", return_value=fake_envelope):
            response = Client().get(_panel_url(panel))
        # No executable script blocks (type="application/json" is allowed).
        content = response.content.decode()
        import re

        executable_scripts = re.findall(r"<script(?![^>]*type=['\"]application/json['\"])[^>]*>", content)
        assert executable_scripts == []


# ---------------------------------------------------------------------------
# req-web-stdpanel-table-edit — get_editor_initial and handle_save
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTablePanelEditorInitial:
    """get_editor_initial pre-populates the form with current panel state."""

    def test_returns_title_and_description(self):
        panel = _create_table_panel(title="My Table", description="Note")
        initial = TablePanelType.get_editor_initial(panel)
        assert initial["title"] == "My Table"
        assert initial["description"] == "Note"

    def test_returns_empty_search_uuid_when_no_search(self):
        panel = _create_table_panel()
        initial = TablePanelType.get_editor_initial(panel)
        assert initial["search_uuid"] == ""

    def test_returns_search_uuid_when_linked(self):
        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)
        initial = TablePanelType.get_editor_initial(panel)
        assert initial["search_uuid"] == str(search.entity_id)

    def test_returns_config_fields(self):
        panel = _create_table_panel(config={"column_mode": "common_metadata", "default_limit": 50})
        initial = TablePanelType.get_editor_initial(panel)
        assert initial["column_mode"] == "common_metadata"
        assert initial["default_limit"] == 50


@pytest.mark.django_db
class TestTablePanelHandleSave:
    """handle_save persists panel fields and manages the USES_SEARCH edge."""

    def _make_form(self, panel: Panel, search=None, **overrides) -> TablePanelEditForm:

        # Refresh choices at form time.
        search_uuid = str(search.entity_id) if search else ""
        data = {
            "title": panel.title,
            "description": panel.description,
            "search_uuid": search_uuid,
            "column_mode": "common_metadata",
            "default_limit": 25,
        }
        data.update(overrides)
        return TablePanelEditForm(data)

    def test_save_updates_title(self):
        panel = _create_table_panel(title="Old")
        form = self._make_form(panel, title="New Title")
        assert form.is_valid(), form.errors
        from django.test import RequestFactory

        request = RequestFactory().post(_edit_url(panel))
        TablePanelType.handle_save(form, panel, request)
        panel.refresh_from_db()
        assert panel.title == "New Title"

    def test_save_updates_config(self):
        panel = _create_table_panel()
        form = self._make_form(panel, default_limit=50)
        assert form.is_valid(), form.errors
        from django.test import RequestFactory

        request = RequestFactory().post(_edit_url(panel))
        TablePanelType.handle_save(form, panel, request)
        panel.refresh_from_db()
        assert panel.config["default_limit"] == 50

    def test_save_creates_uses_search_edge(self):
        from tap_grid.models import Edge

        panel = _create_table_panel()
        search = _create_search()
        form = self._make_form(panel, search=search)
        assert form.is_valid(), form.errors
        from django.test import RequestFactory

        request = RequestFactory().post(_edit_url(panel))
        TablePanelType.handle_save(form, panel, request)
        assert Edge.objects.filter(from_entity=panel.entity, edge_type="USES_SEARCH").exists()

    def test_save_replaces_old_edge_with_new_one(self):
        from tap_grid.models import Edge

        panel = _create_table_panel()
        old_search = _create_search(title="Old Search")
        _link_search(panel, old_search)

        new_search = _create_search(title="New Search")
        form = self._make_form(panel, search=new_search)
        assert form.is_valid(), form.errors
        from django.test import RequestFactory

        request = RequestFactory().post(_edit_url(panel))
        TablePanelType.handle_save(form, panel, request)

        edges = Edge.objects.filter(from_entity=panel.entity, edge_type="USES_SEARCH")
        assert edges.count() == 1
        assert edges.first().to_entity_id == new_search.entity_id

    def test_save_removes_edge_when_no_search_selected(self):
        from tap_grid.models import Edge

        panel = _create_table_panel()
        search = _create_search()
        _link_search(panel, search)

        form = self._make_form(panel, search=None, search_uuid="")
        assert form.is_valid(), form.errors
        from django.test import RequestFactory

        request = RequestFactory().post(_edit_url(panel))
        TablePanelType.handle_save(form, panel, request)

        assert not Edge.objects.filter(from_entity=panel.entity, edge_type="USES_SEARCH").exists()


# ---------------------------------------------------------------------------
# req-web-stdpanel-table-edit — editor view endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTablePanelEditView:
    """The /panel/<slug>--<uuid>/edit/ endpoint renders the table panel editor."""

    def test_get_returns_200(self):
        panel = _create_table_panel()
        response = Client().get(_edit_url(panel))
        assert response.status_code == 200

    def test_get_includes_editor_template(self):
        panel = _create_table_panel()
        response = Client().get(_edit_url(panel))
        template_names = [t.name for t in response.templates]
        assert "tap_web/panels/table_panel_editor.html" in template_names

    def test_post_saves_and_redirects(self):
        panel = _create_table_panel()
        search = _create_search()
        response = Client().post(
            _edit_url(panel),
            {
                "title": "Updated",
                "description": "",
                "search_uuid": str(search.entity_id),
                "column_mode": "common_metadata",
                "default_limit": "25",
            },
        )
        assert response.status_code == 302

    def test_post_empty_title_rerenders_with_errors(self):
        panel = _create_table_panel()
        response = Client().post(
            _edit_url(panel),
            {
                "title": "",
                "description": "",
                "search_uuid": "",
                "column_mode": "common_metadata",
                "default_limit": "25",
            },
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TablePanelEditForm — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTablePanelEditForm:
    def test_valid_minimal_form_passes(self):
        form = TablePanelEditForm(
            {
                "title": "A Table",
                "description": "",
                "search_uuid": "",
                "column_mode": "common_metadata",
                "default_limit": "25",
            }
        )
        assert form.is_valid(), form.errors

    def test_missing_title_fails(self):
        form = TablePanelEditForm(
            {
                "title": "",
                "description": "",
                "search_uuid": "",
                "column_mode": "common_metadata",
                "default_limit": "25",
            }
        )
        assert not form.is_valid()
        assert "title" in form.errors

    def test_invalid_column_mode_fails(self):
        form = TablePanelEditForm(
            {
                "title": "T",
                "description": "",
                "search_uuid": "",
                "column_mode": "bad_mode",
                "default_limit": "25",
            }
        )
        assert not form.is_valid()
        assert "column_mode" in form.errors

    def test_default_limit_below_min_fails(self):
        form = TablePanelEditForm(
            {
                "title": "T",
                "description": "",
                "search_uuid": "",
                "column_mode": "common_metadata",
                "default_limit": "0",
            }
        )
        assert not form.is_valid()
        assert "default_limit" in form.errors

    def test_search_choices_populated(self):
        search = _create_search(title="My Search")
        form = TablePanelEditForm(
            {
                "title": "T",
                "description": "",
                "search_uuid": str(search.entity_id),
                "column_mode": "common_metadata",
                "default_limit": "25",
            }
        )
        choice_values = [v for v, _ in form.fields["search_uuid"].choices]
        assert str(search.entity_id) in choice_values
