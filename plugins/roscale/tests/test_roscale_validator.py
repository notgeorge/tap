"""Validator tests for roscale."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.roscale.parser import parse
from plugins.roscale.validator import validate

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, "rb") as fh:
        return json.load(fh)


class TestSchemaValidation:
    def test_samsite_ssp_schema_ok(self):
        parsed = parse(_load("samsite_oscal_ssp.json"))
        result = validate(parsed)
        assert result.root_recognized
        assert result.schema_ok, [f"{e.path}: {e.message}" for e in result.schema_errors[:5]]

    def test_samsite_poam_schema_ok(self):
        parsed = parse(_load("samsite_oscal_poam.json"))
        result = validate(parsed)
        assert result.root_recognized
        assert result.schema_ok, [f"{e.path}: {e.message}" for e in result.schema_errors[:5]]

    def test_no_root_does_not_validate(self):
        parsed = parse({"not-oscal": {}})
        result = validate(parsed)
        assert not result.root_recognized
        assert not result.schema_ok
        assert result.schema_skipped_reason


class TestSemanticChecksSSP:
    def test_clean_ssp_no_warnings(self):
        parsed = parse(_load("samsite_oscal_ssp.json"))
        result = validate(parsed)
        assert not result.semantic_warnings, [w.message for w in result.semantic_warnings[:5]]

    def test_missing_metadata_warns(self):
        parsed = parse({"system-security-plan": {}})
        result = validate(parsed)
        assert any(w.check == "ssp-metadata-present" for w in result.semantic_warnings)

    def test_missing_title_warns(self):
        parsed = parse(
            {
                "system-security-plan": {
                    "metadata": {"oscal-version": "1.1.2"},
                    "system-characteristics": {},
                }
            }
        )
        result = validate(parsed)
        assert any(w.check == "ssp-metadata-title" for w in result.semantic_warnings)

    def test_missing_control_id_warns(self):
        parsed = parse(
            {
                "system-security-plan": {
                    "metadata": {"title": "T", "oscal-version": "1.1.2"},
                    "system-characteristics": {},
                    "control-implementation": {
                        "implemented-requirements": [
                            {"uuid": "x"},  # missing control-id
                        ]
                    },
                }
            }
        )
        result = validate(parsed)
        assert any(w.check == "ssp-implemented-requirement-control-id" for w in result.semantic_warnings)


class TestSemanticChecksPOAM:
    def test_clean_poam_no_warnings(self):
        parsed = parse(_load("samsite_oscal_poam.json"))
        result = validate(parsed)
        assert not result.semantic_warnings, [w.message for w in result.semantic_warnings[:5]]

    def test_poam_item_without_title_or_description_warns(self):
        parsed = parse(
            {
                "plan-of-action-and-milestones": {
                    "metadata": {"title": "T"},
                    "poam-items": [{"uuid": "x"}],
                }
            }
        )
        result = validate(parsed)
        assert any(w.check == "poam-item-title-or-description" for w in result.semantic_warnings)
