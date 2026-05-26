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
from tap_grid.models import BaseModel, Edge

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
        data = {"columns": {"col-1": {"rows": {"row-1": {}}}}}
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
                FIELD_CRUD_SCHEMA: ClassVar[dict[str, dict]] = {}
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

        page = Page.objects.create(
            name="P",
            slug="/hl-edge-test",
            layout={"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "main"}}}}},
        )
        panel = Panel.objects.create(slug="hl-panel", name="HL Panel", view="tap_web/panel_error.html")
        edge = _make_page_panel_edge(page.entity, panel.entity, "main")

        edge.refresh_from_db()
        hl = edge.properties["hotlink"]
        assert hl["model"] == "page"
        assert hl["spec"] == "page-panels"
        assert hl["value"] == "main"


# ---------------------------------------------------------------------------
# req-grid-hotlink-deferred: deferred validation in batch contexts
# req-grid-service-batch-precommit-consistency: pre-commit consistency phase
# ---------------------------------------------------------------------------


def _page_layout(panel_ids: list[str]) -> dict:
    rows = {f"row-{i + 1}": {"panel-id": pid} for i, pid in enumerate(panel_ids)}
    return {"columns": {"col-1": {"width": "1fr", "rows": rows}}}


class TestDeferredHotlinkQueueMechanics:
    """The ContextVar-backed deferred-hotlink queue (no DB / no batch)."""

    def test_inactive_by_default(self):
        from tap_grid.caller_context import is_deferring_hotlinks

        assert is_deferring_hotlinks() is False

    def test_start_and_reset(self):
        from tap_grid.caller_context import (
            is_deferring_hotlinks,
            reset_deferred_hotlink_checks,
            start_deferred_hotlink_checks,
        )

        token = start_deferred_hotlink_checks()
        assert is_deferring_hotlinks() is True
        reset_deferred_hotlink_checks(token)
        assert is_deferring_hotlinks() is False

    def test_enqueue_noop_when_inactive(self):
        from tap_grid.caller_context import drain_deferred_hotlink_checks, enqueue_deferred_hotlink_check

        # Should not raise, should not enqueue.
        enqueue_deferred_hotlink_check(object())  # type: ignore[arg-type]
        assert drain_deferred_hotlink_checks() == []

    def test_enqueue_and_drain(self):
        from tap_grid.caller_context import (
            drain_deferred_hotlink_checks,
            enqueue_deferred_hotlink_check,
            is_deferring_hotlinks,
            reset_deferred_hotlink_checks,
            start_deferred_hotlink_checks,
        )

        token = start_deferred_hotlink_checks()
        try:
            sentinel_a = object()
            sentinel_b = object()
            enqueue_deferred_hotlink_check(sentinel_a)  # type: ignore[arg-type]
            enqueue_deferred_hotlink_check(sentinel_b)  # type: ignore[arg-type]
            assert is_deferring_hotlinks() is True
            drained = drain_deferred_hotlink_checks()
            assert drained == [sentinel_a, sentinel_b]
            # Drain deactivates deferred mode so re-entrant validate_hotlinks()
            # calls during the drain run inline rather than re-enqueueing.
            assert is_deferring_hotlinks() is False
            # Second drain is a no-op.
            assert drain_deferred_hotlink_checks() == []
        finally:
            reset_deferred_hotlink_checks(token)


@pytest.mark.django_db
class TestDeferredHotlinkInWriteBatch:
    """write_batch defers validate_hotlinks() and drains pre-commit."""

    def _make_panel(self, slug: str):
        from tap_web.models import Panel

        return Panel.objects.create(slug=slug, name=slug, view="tap_web/panel_error.html")

    def test_inline_save_outside_batch_still_validates(self):
        """Direct model.save() (no write_batch) keeps inline hotlink validation."""
        from tap_web.models import Page

        # Create a page with no edges.
        page = Page(name="Solo", slug="/solo-deferred", layout=_page_layout(["nope"]))
        page.save(skip_validation=True)
        # Now full_validate (called by future save) should fail inline since
        # no deferral context is active.
        with pytest.raises(ValidationError):
            page.full_validate()

    def test_upsert_with_new_edge_in_same_batch_succeeds(self):
        """Page layout references a panel-id whose edge is created in the SAME batch.

        This is the originating bug: validate_hotlinks ran inline during the
        per-op pipeline for replace_node and saw the OLD edge set (no edge for
        the new panel-id). With deferred validation, the drain runs after both
        the node replace and the new edge create have landed, so the validator
        sees the post-batch edge set.
        """
        import uuid

        from tap_grid.service_types import WriteOperation
        from tap_grid.services import write_batch
        from tap_web.models import Page

        # Initial state: page with panel "a", matching edge.
        panel_a = self._make_panel("p-a")
        page = Page.objects.create(name="P", slug="/upsert-new-edge", layout=_page_layout(["a"]))
        _make_page_panel_edge(page.entity, panel_a.entity, "a")

        # Add panel "b" up front (a real entity to point a new edge at).
        panel_b = self._make_panel("p-b")

        # Batch: replace page to reference both "a" and "b", AND create the
        # USES_PANEL edge for "b" in the same batch.
        new_edge_id = str(uuid.uuid4())
        result = write_batch(
            [
                WriteOperation(
                    verb="replace_node",
                    target=str(page.entity_id),
                    payload={
                        "name": "P",
                        "slug": "/upsert-new-edge",
                        "description": "",
                        "layout": _page_layout(["a", "b"]),
                    },
                ),
                WriteOperation(
                    verb="create_edge",
                    from_target=str(page.entity_id),
                    to_target=str(panel_b.entity_id),
                    edge_type="USES_PANEL",
                    payload={"properties": {"hotlink": {"model": "page", "spec": "page-panels", "value": "b"}}},
                    entity_id=new_edge_id,
                ),
            ]
        )

        assert result.success, result.results
        page.refresh_from_db()
        assert "row-2" in page.layout["columns"]["col-1"]["rows"]

    def test_upsert_with_missing_edge_fails_with_per_op_attribution(self):
        """Layout references a panel-id with no matching edge anywhere — failure
        attributed to the replace_node op via hotlink_validation_failed."""
        from tap_grid.service_types import WriteOperation
        from tap_grid.services import write_batch
        from tap_web.models import Page

        panel_a = self._make_panel("attr-a")
        page = Page.objects.create(name="P", slug="/attr-fail", layout=_page_layout(["a"]))
        _make_page_panel_edge(page.entity, panel_a.entity, "a")

        # Revise layout to add "missing"; do NOT create the matching edge.
        result = write_batch(
            [
                WriteOperation(
                    verb="replace_node",
                    target=str(page.entity_id),
                    payload={
                        "name": "P",
                        "slug": "/attr-fail",
                        "description": "",
                        "layout": _page_layout(["a", "missing"]),
                    },
                ),
            ]
        )

        assert result.success is False
        assert len(result.results) == 1
        offending = result.results[0]
        assert offending.success is False
        codes = {e.code for e in offending.errors}
        assert "hotlink_validation_failed" in codes
        # Rollback: the page on disk still references just "a".
        page.refresh_from_db()
        assert page.layout == _page_layout(["a"])

    def test_drain_collects_all_failures_across_multiple_pages(self):
        """Two failing pages in one batch both attributed; no first-fail bail."""
        from tap_grid.service_types import WriteOperation
        from tap_grid.services import write_batch
        from tap_web.models import Page

        # Two pages, each with one valid edge.
        panel_x = self._make_panel("multi-x")
        panel_y = self._make_panel("multi-y")
        page1 = Page.objects.create(name="P1", slug="/multi-1", layout=_page_layout(["x"]))
        page2 = Page.objects.create(name="P2", slug="/multi-2", layout=_page_layout(["y"]))
        _make_page_panel_edge(page1.entity, panel_x.entity, "x")
        _make_page_panel_edge(page2.entity, panel_y.entity, "y")

        # Batch: replace both pages with layouts that reference panel-ids that
        # have no matching edges. Neither replace adds the needed edge.
        result = write_batch(
            [
                WriteOperation(
                    verb="replace_node",
                    target=str(page1.entity_id),
                    payload={
                        "name": "P1",
                        "slug": "/multi-1",
                        "description": "",
                        "layout": _page_layout(["x", "missing-1"]),
                    },
                ),
                WriteOperation(
                    verb="replace_node",
                    target=str(page2.entity_id),
                    payload={
                        "name": "P2",
                        "slug": "/multi-2",
                        "description": "",
                        "layout": _page_layout(["y", "missing-2"]),
                    },
                ),
            ]
        )

        assert result.success is False
        # Both per-op results should carry hotlink errors (not just the first).
        op1, op2 = result.results
        assert op1.success is False
        assert op2.success is False
        assert any(e.code == "hotlink_validation_failed" for e in op1.errors)
        assert any(e.code == "hotlink_validation_failed" for e in op2.errors)

    def test_fresh_create_with_edge_in_same_batch_succeeds(self):
        """A brand-new page (entity_id None at enqueue) whose USES_PANEL edge
        lands in the same batch validates correctly post-drain."""
        import uuid

        from tap_grid.service_types import WriteOperation
        from tap_grid.services import write_batch

        panel = self._make_panel("fresh-create-panel")

        new_page_id = str(uuid.uuid4())
        new_edge_id = str(uuid.uuid4())
        result = write_batch(
            [
                WriteOperation(
                    verb="create_node",
                    type_slug="page",
                    payload={
                        "name": "Fresh",
                        "slug": "/fresh-create",
                        "description": "",
                        "layout": _page_layout(["only"]),
                    },
                    entity_id=new_page_id,
                ),
                WriteOperation(
                    verb="create_edge",
                    from_target=new_page_id,
                    to_target=str(panel.entity_id),
                    edge_type="USES_PANEL",
                    payload={"properties": {"hotlink": {"model": "page", "spec": "page-panels", "value": "only"}}},
                    entity_id=new_edge_id,
                ),
            ]
        )
        assert result.success, result.results

    def test_dry_run_drain_runs_and_rolls_back(self):
        """Dry-run still runs the consistency phase; failure surfaces; nothing persists."""
        from tap_grid.service_types import WriteOperation
        from tap_grid.services import write_batch
        from tap_web.models import Page

        panel = self._make_panel("dry-run")
        page = Page.objects.create(name="P", slug="/dry-run-page", layout=_page_layout(["ok"]))
        _make_page_panel_edge(page.entity, panel.entity, "ok")
        original_layout = dict(page.layout)

        result = write_batch(
            [
                WriteOperation(
                    verb="replace_node",
                    target=str(page.entity_id),
                    payload={
                        "name": "P",
                        "slug": "/dry-run-page",
                        "description": "",
                        "layout": _page_layout(["ok", "ghost"]),
                    },
                ),
            ],
            dry_run=True,
        )

        # Dry-run failure surfaces; page on disk unchanged.
        assert result.success is False
        assert any(e.code == "hotlink_validation_failed" for e in result.results[0].errors)
        page.refresh_from_db()
        assert page.layout == original_layout
