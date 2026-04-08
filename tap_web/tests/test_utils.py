"""Tests for tap_web.utils — req-web-panel-json-embed.sec."""

import json

import pytest

from tap_web.utils import safe_json


class TestSafeJson:
    """req-web-panel-json-embed.sec: Script-Context JSON Embedding Security."""

    def test_plain_value_round_trips(self):
        value = {"name": "Gandalf", "count": 42}
        assert json.loads(safe_json(value)) == value

    def test_list_round_trips(self):
        value = [1, "two", None, True]
        assert json.loads(safe_json(value)) == value

    def test_escapes_script_close_tag(self):
        """ACID req-web-panel-json-embed.sec-4: </script> breakout prevented."""
        payload = '</script><script>alert(1)</script>'
        result = safe_json(payload)
        assert "<" not in result
        assert ">" not in result
        # Still deserializes to the original string.
        assert json.loads(result) == payload

    def test_escapes_lt_gt_amp(self):
        """ACID req-web-panel-json-embed.sec-2: Unicode escape applied."""
        payload = "<b>bold</b> & more"
        result = safe_json(payload)
        assert r"\u003c" in result
        assert r"\u003e" in result
        assert r"\u0026" in result
        assert json.loads(result) == payload

    def test_html_comment_injection(self):
        payload = "<!-- comment -->"
        result = safe_json(payload)
        assert "<!--" not in result
        assert json.loads(result) == payload

    def test_nested_structure_escapes(self):
        value = {"html": "<div>hi</div>", "items": ["a&b", "c>d"]}
        result = safe_json(value)
        assert "<" not in result
        assert ">" not in result
        assert "&" not in result
        assert json.loads(result) == value

    def test_empty_structures(self):
        assert safe_json([]) == "[]"
        assert safe_json({}) == "{}"

    def test_string_type_returned(self):
        assert isinstance(safe_json({"a": 1}), str)
