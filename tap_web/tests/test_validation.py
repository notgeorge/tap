"""Tests for tap_web validation utilities.

Covers:
  req-web-page-slug-sanitize.sec — Page slug normalization and security rules
  req-web-page-layout-sanitize.sec — Page layout JSON Schema validation
"""

import pytest

from tap_web.exceptions import (
    PageLayoutValidationError,
    PageSlugValidationError,
)
from tap_web.validation import validate_page_layout, validate_page_slug

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_LAYOUT = {
    "columns": {
        "col-1": {
            "width": "1fr",
            "rows": {
                "row-1": {"panel-id": "main"},
            },
        }
    }
}


# ---------------------------------------------------------------------------
# Page slug validation (req-web-page-slug-sanitize.sec)
# ---------------------------------------------------------------------------


class TestValidatePageSlug:
    def test_valid_slug_passes(self):
        validate_page_slug("/my-page")

    def test_valid_nested_slug_passes(self):
        validate_page_slug("/section/sub-page")

    def test_must_start_with_slash(self):
        with pytest.raises(PageSlugValidationError, match="must start with"):
            validate_page_slug("no-leading-slash")

    def test_root_slash_is_invalid(self):
        with pytest.raises(PageSlugValidationError, match="reserved for the root URL"):
            validate_page_slug("/")

    def test_uppercase_rejected(self):
        with pytest.raises(PageSlugValidationError, match="lowercase"):
            validate_page_slug("/My-Page")

    def test_repeated_slashes_rejected(self):
        with pytest.raises(PageSlugValidationError, match="repeated slashes"):
            validate_page_slug("/foo//bar")

    def test_trailing_slash_rejected(self):
        with pytest.raises(PageSlugValidationError, match="trailing slash"):
            validate_page_slug("/foo/")

    def test_dot_segment_rejected(self):
        with pytest.raises(PageSlugValidationError, match="dot-segment"):
            validate_page_slug("/foo/./bar")

    def test_double_dot_segment_rejected(self):
        with pytest.raises(PageSlugValidationError, match="dot-segment"):
            validate_page_slug("/foo/../bar")

    def test_trailing_standalone_dot_rejected(self):
        # /foo/. is a standalone dot segment at end (req-web-page-slug-sanitize.sec-8)
        with pytest.raises(PageSlugValidationError, match="dot-segment"):
            validate_page_slug("/foo/.")

    def test_reserved_prefix_blocked(self):
        with pytest.raises(PageSlugValidationError, match="reserved prefix"):
            validate_page_slug("/admin", reserved_prefixes=["/admin"])

    def test_reserved_prefix_blocks_subpath(self):
        with pytest.raises(PageSlugValidationError, match="reserved prefix"):
            validate_page_slug("/admin/settings", reserved_prefixes=["/admin"])

    def test_similar_but_not_reserved_passes(self):
        # /admins is NOT blocked by /admin
        validate_page_slug("/admins", reserved_prefixes=["/admin"])

    def test_no_reserved_prefixes_is_fine(self):
        validate_page_slug("/anything", reserved_prefixes=None)


# ---------------------------------------------------------------------------
# Page layout validation (req-web-page-layout-sanitize.sec)
# ---------------------------------------------------------------------------


class TestValidatePageLayout:
    def test_valid_layout_passes(self):
        validate_page_layout(_VALID_LAYOUT)

    def test_valid_layout_with_spans_passes(self):
        layout = {
            "columns": {
                "col-1": {
                    "width": "2fr",
                    "rows": {
                        "row-1": {"panel-id": "left", "row_span": 2, "col_span": 1},
                    },
                },
                "col-2": {
                    "width": "1fr",
                    "rows": {
                        "row-1": {"panel-id": "right"},
                    },
                },
            }
        }
        validate_page_layout(layout)

    def test_valid_layout_with_tags_passes(self):
        layout = {
            "columns": {
                "col-1-main": {
                    "width": "1fr",
                    "tags": {"role": "primary"},
                    "rows": {
                        "row-1": {"panel-id": "main", "tags": {"size": "large"}},
                    },
                }
            }
        }
        validate_page_layout(layout)

    def test_missing_columns_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout({})

    def test_empty_columns_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout({"columns": {}})

    def test_invalid_column_key_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout({"columns": {"column-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "x"}}}}})

    def test_invalid_width_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout({"columns": {"col-1": {"width": "50%", "rows": {"row-1": {"panel-id": "x"}}}}})

    def test_missing_panel_id_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout({"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {}}}}})

    def test_invalid_panel_id_format_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout({"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "My Panel"}}}}})

    def test_invalid_row_key_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout({"columns": {"col-1": {"width": "1fr", "rows": {"Row1": {"panel-id": "x"}}}}})

    def test_row_span_zero_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout(
                {"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "x", "row_span": 0}}}}}
            )

    def test_unknown_top_level_key_raises(self):
        with pytest.raises(PageLayoutValidationError):
            validate_page_layout(
                {"columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "x"}}}}, "extra": 1}
            )


# ---------------------------------------------------------------------------
# Panel static asset validation (req-web-panel-static)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Model-level full_validate() hooks (req-web-page-slug-sanitize.sec,
# req-web-page-layout-sanitize.sec)
# ---------------------------------------------------------------------------


class TestPageFullValidate:
    """Page.full_validate() enforces slug and layout constraints via validate() hooks."""

    def _make_page(self, **kwargs):
        from tap_web.models import Page

        defaults = {
            "name": "Test Page",
            "slug": "/test-page",
            "layout": {
                "columns": {
                    "col-1": {
                        "width": "1fr",
                        "rows": {"row-1": {"panel-id": "main"}},
                    }
                }
            },
        }
        defaults.update(kwargs)
        return Page(**defaults)

    def test_valid_page_passes(self):
        page = self._make_page()
        page.full_validate()  # no exception

    def test_invalid_slug_raises_validation_error(self):
        from django.core.exceptions import ValidationError

        page = self._make_page(slug="no-leading-slash")
        with pytest.raises(ValidationError) as exc_info:
            page.full_validate()
        assert "slug" in exc_info.value.message_dict

    def test_invalid_layout_raises_validation_error(self):
        from django.core.exceptions import ValidationError

        page = self._make_page(layout={"columns": {}})  # empty columns is invalid
        with pytest.raises(ValidationError) as exc_info:
            page.full_validate()
        assert "layout" in exc_info.value.message_dict


