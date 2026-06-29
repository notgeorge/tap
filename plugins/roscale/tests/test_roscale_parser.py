"""Parser tests for roscale."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.roscale.parser import detect_root, parse

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, "rb") as fh:
        return json.load(fh)


class TestDetectRoot:
    def test_ssp_root(self):
        assert detect_root({"system-security-plan": {}}) == "system-security-plan"

    def test_poam_root(self):
        assert detect_root({"plan-of-action-and-milestones": {}}) == "plan-of-action-and-milestones"

    def test_catalog_root(self):
        assert detect_root({"catalog": {}}) == "catalog"

    def test_no_root(self):
        assert detect_root({"not-oscal": {}, "$schema": "x"}) is None

    def test_multiple_roots_returns_none(self):
        # Multiple OSCAL roots at top level is invalid; parser must surface that.
        assert detect_root({"catalog": {}, "profile": {}}) is None


class TestParseDict:
    def test_samsite_ssp(self):
        result = parse(_load("samsite_oscal_ssp.json"))
        assert result.ok
        assert result.root_key == "system-security-plan"
        assert result.document_type == "ssp"
        assert result.errors == []

    def test_samsite_poam(self):
        result = parse(_load("samsite_oscal_poam.json"))
        assert result.ok
        assert result.root_key == "plan-of-action-and-milestones"
        assert result.document_type == "poam"
        assert result.errors == []


class TestParseJsonString:
    def test_ssp_string(self):
        raw = (FIXTURES / "samsite_oscal_ssp.json").read_text()
        result = parse(raw)
        assert result.ok
        assert result.root_key == "system-security-plan"

    def test_invalid_json(self):
        result = parse("{not valid json")
        assert not result.ok
        assert result.document is None
        assert any(e.phase == "json-parse" for e in result.errors)


class TestParseEntityLike:
    class _FakeNode:
        def __init__(self, content, entity_type=None):
            self.content = content
            if entity_type is not None:
                self.entity_type = entity_type

    def test_entity_with_dict_content(self):
        node = self._FakeNode(content=_load("samsite_oscal_ssp.json"), entity_type="compliance_artifact")
        result = parse(node)
        assert result.ok
        assert result.root_key == "system-security-plan"
        assert result.warnings == []

    def test_unexpected_entity_type_warns_not_fails(self):
        node = self._FakeNode(content=_load("samsite_oscal_ssp.json"), entity_type="random_node")
        result = parse(node)
        assert result.ok
        assert any("preferred is 'compliance_artifact'" in w.message for w in result.warnings)


class TestParseFailures:
    def test_no_oscal_root(self):
        result = parse({"not-an-oscal-document": {"some": "data"}})
        assert not result.ok
        assert result.root_key is None
        assert any(e.phase == "root-detect" for e in result.errors)

    def test_unsupported_source_type(self):
        result = parse(42)
        assert not result.ok
        assert any(e.phase == "source" for e in result.errors)
