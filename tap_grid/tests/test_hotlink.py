"""Tests for the TAP hotlink system.

Covers:
  req-grid-hotlink-model    — _check_hotlinks startup validation
  req-grid-hotlink-selector — simple_path extraction
  req-grid-hotlink-validation — validate_hotlinks (exact / exists / unique modes)
  req-grid-hotlink-edge-data  — edge properties.hotlink format
"""

from typing import ClassVar

import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models

from tap_grid.hotlink import (
    _check_hotlinks,
    _simple_path_extract,
    extract_identifiers,
    validate_hotlinks,
)
from tap_grid.models import BaseModel, Edge, Entity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cls(hotlinks):
    """Return a bare class whose __dict__ contains HOTLINKS — for _check_hotlinks tests."""
    return type("FakeModel", (), {"HOTLINKS": hotlinks})


def _make_page_panel_edge(page_entity, panel_entity, panel_id: str) -> Edge:
    """Create a USES_PANEL edge with the canonical hotlink properties format."""
    return Edge.objects.create(
        from_entity=page_entity,
        to_entity=panel_entity,
        edge_type="USES_PANEL",
        properties={"hotlink": {"model": "page", "spec": "page-panels", "value": panel_id}},
    )


# ---------------------------------------------------------------------------
# req-grid-hotlink-selector: simple_path extraction
# ---------------------------------------------------------------------------

class TestSimplePathExtract:
    """Unit tests for _simple_path_extract — no DB required."""

    def test_single_key(self):
        assert _simple_path_extract({"a": "x"}, "a") == {"x"}

    def test_nested_keys(self):
        assert _simple_path_extract({"a": {"b": "y"}}, "a.b") == {"y"}

    def test_wildcard_over_dict(self):
        data = {"columns": {"col-1": "a", "col-2": "b"}}
        assert _simple_path_extract(data, "columns.*") == {"a", "b"}

    def test_wildcard_over_list(self):
        data = {"items": [1, 2, 3]}
        assert _simple_path_extract(data, "items.*") == {"1", "2", "3"}

    def test_page_layout_pattern(self):
        """The canonical page layout selector extracts panel-id values."""
        layout = {
            "columns": {
                "col-1": {
                    "rows": {
                        "row-1": {"panel-id": "graph"},
                        "row-2": {"panel-id": "nodes"},
                    }
                },
                "col-2": {
                    "rows": {
                        "row-1": {"panel-id": "sidebar"},
                    }
                },
            }
        }
        result = _simple_path_extract(layout, "columns.*.rows.*.panel-id")
        assert result == {"graph", "nodes", "sidebar"}

    def test_missing_key_returns_empty(self):
        assert _simple_path_extract({"a": "x"}, "b") == set()

    def test_missing_nested_key_skips_silently(self):
        data = {"columns": {"col-1": {"rows": {"row-1": {}}}}
        }
        result = _simple_path_extract(data, "columns.*.rows.*.panel-id")
        assert result == set()

    def test_none_values_excluded(self):
        data = {"columns": {"col-1": {"rows": {"row-1": {"panel-id": None}}}}}
        result = _simple_path_extract(data, "columns.*.rows.*.panel-id")
        assert result == set()

    def test_non_traversable_node_skipped(self):
        """A string node at a wildcard position is silently skipped."""
        data = {"columns": "not-a-dict"}
        assert _simple_path_extract(data, "columns.*.id") == set()

    def test_empty_layout_returns_empty(self):
        assert _simple_path_extract({}, "columns.*.rows.*.panel-id") == set()

    def test_values_coerced_to_string(self):
        data = {"ids": {"a": 42, "b": True}}
        result = _simple_path_extract(data, "ids.*")
        assert result == {"42", "True"}


class TestExtractIdentifiersDispatch:
    """extract_identifiers dispatches to the correct backend."""

    def test_simple_path_dispatched(self):
        result = extract_identifiers({"key": "v"}, "simple_path", "key")
        assert result == {"v"}

    def test_unknown_selector_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported selector_type"):
            extract_identifiers({}, "jsonpath", "$.key")


# ---------------------------------------------------------------------------
# req-grid-hotlink-model: _check_hotlinks startup validation
# ---------------------------------------------------------------------------

class TestCheckHotlinks:
    """Startup invariant checks — no DB required."""

    _VALID = {
        "name": "page-panels",
        "field": "layout",
        "selector_type": "simple_path",
        "selector": "columns.*.rows.*.panel-id",
        "edge_direction": "outbound",
        "edge_type": "USES_PANEL",
        "mode": "exact",
    }

    def test_valid_definition_passes(self):
        _check_hotlinks(_cls([self._VALID]))

    def test_empty_list_passes(self):
        _check_hotlinks(_cls([]))

    def test_hotlinks_not_a_list_raises(self):
        with pytest.raises(ImproperlyConfigured, match="must be a list"):
            _check_hotlinks(_cls({"name": "x"}))

    def test_entry_not_a_dict_raises(self):
        with pytest.raises(ImproperlyConfigured, match="each entry must be a dict"):
            _check_hotlinks(_cls(["not-a-dict"]))

    def test_missing_required_key_raises(self):
        bad = {k: v for k, v in self._VALID.items() if k != "mode"}
        with pytest.raises(ImproperlyConfigured, match="missing required keys"):
            _check_hotlinks(_cls([bad]))

    def test_empty_name_raises(self):
        bad = {**self._VALID, "name": ""}
        with pytest.raises(ImproperlyConfigured, match="non-empty string"):
            _check_hotlinks(_cls([bad]))

    def test_duplicate_name_raises(self):
        with pytest.raises(ImproperlyConfigured, match="duplicate hotlink name"):
            _check_hotlinks(_cls([self._VALID, self._VALID]))

    def test_invalid_selector_type_raises(self):
        bad = {**self._VALID, "selector_type": "jsonpath"}
        with pytest.raises(ImproperlyConfigured, match="selector_type"):
            _check_hotlinks(_cls([bad]))

    def test_invalid_edge_direction_raises(self):
        bad = {**self._VALID, "edge_direction": "sideways"}
        with pytest.raises(ImproperlyConfigured, match="edge_direction"):
            _check_hotlinks(_cls([bad]))

    def test_invalid_mode_raises(self):
        bad = {**self._VALID, "mode": "fuzzy"}
        with pytest.raises(ImproperlyConfigured, match="mode"):
            _check_hotlinks(_cls([bad]))

    def test_multiple_valid_definitions_pass(self):
        second = {**self._VALID, "name": "page-other", "edge_type": "USES_OTHER"}
        _check_hotlinks(_cls([self._VALID, second]))

    def test_basemodel_subclass_with_bad_hotlinks_raises_at_definition_time(self):
        """__init_subclass__ propagates ImproperlyConfigured from _check_hotlinks."""
        with pytest.raises(ImproperlyConfigured, match="mode"):
            # Defining this class triggers __init_subclass__ → _check_hotlinks.
            class _BadPage(BaseModel):
                entity = models.OneToOneField(
                    "tap_grid.Entity",
                    on_delete=models.DO_NOTHING,
                    related_name="+",
                )
                ENTITY_TYPE: ClassVar[str] = "bad_page_type_x"
                HOTLINKS: ClassVar[list[dict]] = [
                    {
                        "name": "x",
                        "field": "layout",
                        "selector_type": "simple_path",
                        "selector": "columns.*",
                        "edge_direction": "outbound",
                        "edge_type": "USES_PANEL",
                        "mode": "invalid_mode",
                    }
                ]

                class Meta(BaseModel.Meta):
                    abstract = True


# ---------------------------------------------------------------------------
# req-grid-hotlink-validation: validate_hotlinks (DB integration)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestValidateHotlinksExactMode:
    """validate_hotlinks with mode='exact' — uses Page model directly."""

    def _make_page(self, panel_ids: list[str]):
        """Create a Page whose layout references the given panel_ids (unsaved form)."""
        from tap_web.models import Page

        rows = {f"row-{i + 1}": {"panel-id": pid} for i, pid in enumerate(panel_ids)}
        layout = {"columns": {"col-1": {"width": "1fr", "rows": rows}}}
        page = Page(name="Test Page", slug=f"/test-hotlink-{'-'.join(panel_ids)}", layout=layout)
        page.save(skip_validation=True)  # skip so hotlink validation doesn't run on first save
        return page

    def _make_panel(self):
        from tap_web.models import Panel

        return Panel.objects.create(
            slug="test-panel",
            name="Test Panel",
            view="tap_web/panel_error.html",
        )

    def test_first_save_skips_validation(self):
        """New Page (entity_id None) bypasses hotlink validation (Option A)."""
        from tap_web.models import Page

        layout = {"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "orphan"}}}}}
        # This should not raise — first save, no edges exist yet.
        page = Page.objects.create(name="New Page", slug="/test-first-save", layout=layout)
        assert page.entity_id is not None

    def test_exact_passes_when_ids_match(self):
        """validate_hotlinks passes when extracted IDs equal edge hotlink.value set."""
        page = self._make_page(["main"])
        panel = self._make_panel()
        _make_page_panel_edge(page.entity, panel.entity, "main")

        # Should not raise.
        validate_hotlinks(page)

    def test_exact_fails_missing_edge(self):
        """Layout references a panel-id with no corresponding edge."""
        page = self._make_page(["main"])
        # No edge created → exact mode fails.
        with pytest.raises(ValidationError) as exc_info:
            validate_hotlinks(page)
        assert "missing edges" in str(exc_info.value)

    def test_exact_fails_extra_edge(self):
        """An edge exists whose hotlink.value has no matching panel-id in layout."""
        # Page references "main"; edge carries "orphan" — mismatch on both sides.
        page = self._make_page(["main"])
        panel = self._make_panel()
        _make_page_panel_edge(page.entity, panel.entity, "orphan")

        with pytest.raises(ValidationError) as exc_info:
            validate_hotlinks(page)
        assert "extra edges" in str(exc_info.value)

    def test_exact_fails_mismatch(self):
        """Layout has 'main', edge has 'other' — both sides of the diff reported."""
        page = self._make_page(["main"])
        panel = self._make_panel()
        _make_page_panel_edge(page.entity, panel.entity, "other")

        with pytest.raises(ValidationError) as exc_info:
            validate_hotlinks(page)
        msg = str(exc_info.value)
        assert "missing edges" in msg
        assert "extra edges" in msg

    def test_exact_passes_multiple_panels(self):
        """Multiple panel slots all matched by edges."""
        from tap_web.models import Panel

        page = self._make_page(["graph", "nodes"])
        panel_a = self._make_panel()
        panel_b = Panel.objects.create(slug="panel-b", name="Panel B", view="tap_web/panel_error.html")
        _make_page_panel_edge(page.entity, panel_a.entity, "graph")
        _make_page_panel_edge(page.entity, panel_b.entity, "nodes")

        validate_hotlinks(page)  # no exception

    def test_only_matching_spec_edges_counted(self):
        """Edges with a different hotlink.spec are ignored by validation."""
        page = self._make_page(["main"])
        panel = self._make_panel()

        # Edge with wrong spec — should not satisfy the 'main' requirement.
        Edge.objects.create(
            from_entity=page.entity,
            to_entity=panel.entity,
            edge_type="USES_PANEL",
            properties={"hotlink": {"model": "page", "spec": "other-spec", "value": "main"}},
        )

        with pytest.raises(ValidationError) as exc_info:
            validate_hotlinks(page)
        assert "missing edges" in str(exc_info.value)

    def test_edges_without_hotlink_key_ignored(self):
        """Edges whose properties lack a 'hotlink' key are not counted as participants.

        The USES_PANEL edge schema now requires 'hotlink', so this state can only
        arise from direct DB manipulation (e.g. pre-migration data). We simulate it
        via a queryset update to bypass model-level save validation.
        """
        page = self._make_page(["main"])
        panel = self._make_panel()

        # Create a valid hotlink edge then overwrite properties directly in the DB.
        edge = _make_page_panel_edge(page.entity, panel.entity, "main")
        Edge.objects.filter(pk=edge.pk).update(properties={"panel-id": "main"})

        # The validator ignores the edge — missing hotlink key means no participation.
        with pytest.raises(ValidationError):
            validate_hotlinks(page)

    def test_unsaved_instance_skipped(self):
        """Instance with entity_id=None is skipped (Option A)."""
        from tap_web.models import Page

        layout = {"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "x"}}}}}
        page = Page(name="Unsaved", slug="/unsaved-test", layout=layout)
        # entity_id is None at this point — should not raise.
        validate_hotlinks(page)


@pytest.mark.django_db
class TestValidateHotlinksExistsMode:
    """validate_hotlinks with mode='exists'."""

    def _make_model_with_exists_hotlink(self):
        """Monkeypatch a Page instance to use 'exists' mode for testing."""
        from tap_web.models import Page

        page = Page(
            name="Exists Test",
            slug="/exists-test",
            layout={"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "x"}}}}},
        )
        page.save(skip_validation=True)

        # Temporarily override HOTLINKS on the instance's class for the test.
        orig = Page.HOTLINKS
        Page.HOTLINKS = [
            {
                "name": "page-panels",
                "field": "layout",
                "selector_type": "simple_path",
                "selector": "columns.*.rows.*.panel-id",
                "edge_direction": "outbound",
                "edge_type": "USES_PANEL",
                "mode": "exists",
            }
        ]
        return page, orig

    def test_exists_passes_when_edge_present(self):
        from tap_web.models import Page, Panel

        page, orig = self._make_model_with_exists_hotlink()
        try:
            panel = Panel.objects.create(slug="ep", name="EP", view="tap_web/panel_error.html")
            _make_page_panel_edge(page.entity, panel.entity, "x")
            validate_hotlinks(page)  # no exception
        finally:
            Page.HOTLINKS = orig

    def test_exists_fails_when_edge_missing(self):
        from tap_web.models import Page

        page, orig = self._make_model_with_exists_hotlink()
        try:
            with pytest.raises(ValidationError, match="no edge found"):
                validate_hotlinks(page)
        finally:
            Page.HOTLINKS = orig

    def test_exists_passes_with_extra_edges(self):
        """exists mode does not fail when extra edges exist (only checks presence)."""
        from tap_web.models import Page, Panel

        page, orig = self._make_model_with_exists_hotlink()
        try:
            panel_a = Panel.objects.create(slug="epa", name="EPA", view="tap_web/panel_error.html")
            panel_b = Panel.objects.create(slug="epb", name="EPB", view="tap_web/panel_error.html")
            _make_page_panel_edge(page.entity, panel_a.entity, "x")
            _make_page_panel_edge(page.entity, panel_b.entity, "extra")
            validate_hotlinks(page)  # no exception — 'x' is satisfied; 'extra' is irrelevant
        finally:
            Page.HOTLINKS = orig


@pytest.mark.django_db
class TestValidateHotlinksUniqueMode:
    """validate_hotlinks with mode='unique'."""

    def _make_model_with_unique_hotlink(self):
        from tap_web.models import Page

        page = Page(
            name="Unique Test",
            slug="/unique-test",
            layout={"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "x"}}}}},
        )
        page.save(skip_validation=True)

        orig = Page.HOTLINKS
        Page.HOTLINKS = [
            {
                "name": "page-panels",
                "field": "layout",
                "selector_type": "simple_path",
                "selector": "columns.*.rows.*.panel-id",
                "edge_direction": "outbound",
                "edge_type": "USES_PANEL",
                "mode": "unique",
            }
        ]
        return page, orig

    def test_unique_passes_with_single_matching_edge(self):
        from tap_web.models import Page, Panel

        page, orig = self._make_model_with_unique_hotlink()
        try:
            panel = Panel.objects.create(slug="up", name="UP", view="tap_web/panel_error.html")
            _make_page_panel_edge(page.entity, panel.entity, "x")
            validate_hotlinks(page)  # no exception
        finally:
            Page.HOTLINKS = orig

    def test_unique_fails_with_duplicate_edges(self):
        from tap_web.models import Page, Panel

        page, orig = self._make_model_with_unique_hotlink()
        try:
            panel_a = Panel.objects.create(slug="ua", name="UA", view="tap_web/panel_error.html")
            panel_b = Panel.objects.create(slug="ub", name="UB", view="tap_web/panel_error.html")
            _make_page_panel_edge(page.entity, panel_a.entity, "x")
            _make_page_panel_edge(page.entity, panel_b.entity, "x")
            with pytest.raises(ValidationError, match="multiple edges found"):
                validate_hotlinks(page)
        finally:
            Page.HOTLINKS = orig

    def test_unique_fails_with_missing_edge(self):
        from tap_web.models import Page

        page, orig = self._make_model_with_unique_hotlink()
        try:
            with pytest.raises(ValidationError, match="no edge found"):
                validate_hotlinks(page)
        finally:
            Page.HOTLINKS = orig


# ---------------------------------------------------------------------------
# req-grid-hotlink-edge-data: edge properties.hotlink structure
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHotlinkEdgeData:
    """Edges carry the canonical properties.hotlink object."""

    def test_hotlink_object_stored_on_edge(self):
        """Edge created with hotlink format retains all three fields."""
        from tap_web.models import Page, Panel

        page = Page.objects.create(name="P", slug="/hl-edge-test", layout={
            "columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "main"}}}}
        })
        panel = Panel.objects.create(slug="hl-panel", name="HL Panel", view="tap_web/panel_error.html")
        edge = _make_page_panel_edge(page.entity, panel.entity, "main")

        edge.refresh_from_db()
        hl = edge.properties["hotlink"]
        assert hl["model"] == "page"
        assert hl["spec"] == "page-panels"
        assert hl["value"] == "main"
