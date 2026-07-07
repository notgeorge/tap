"""Scoring tests for the KSI scoreboard.

Pure-function tests against the roscale fixture OSCAL artifacts plus a
synthetic indicator catalog. No Django setup needed.
"""

from __future__ import annotations

import json

from tap_plugin.samsite.scoring import (
    CONTROL_NA,
    CONTROL_OPEN,
    CONTROL_PASS,
    CONTROL_UNMAPPED,
    INDICATOR_GAP,
    INDICATOR_IN_PROGRESS,
    INDICATOR_PASSING,
    group_by_theme,
    score,
)

from tap.plugin_testing import plugin_package_dir

_roscale = plugin_package_dir("roscale")
assert _roscale is not None, "roscale must be installed for samsite scoreboard tests"
FIXTURES = _roscale / "tests" / "fixtures"


def _ssp() -> dict:
    return json.loads((FIXTURES / "samsite_oscal_ssp.json").read_text())


def _poam() -> dict:
    return json.loads((FIXTURES / "samsite_oscal_poam.json").read_text())


class TestSystemClassDetection:
    def test_reads_fedramp_class_c_from_samsite_ssp(self):
        result = score(indicators=[], ssp_doc=_ssp(), poam_doc=_poam())
        assert result.system_class == "c"


class TestControlEvaluation:
    """Smoke tests against the live Samsite SSP — control statuses must match."""

    def test_ac_2_in_ssp_appears_in_poam_open(self):
        # POAM-001 references "ia-2, ia-5, ac-2" with status=open.
        indicator = {
            "code": "KSI-TEST-AC2",
            "name": "AC-2 only",
            "classes": ["c"],
            "controls": ["ac-2"],
        }
        result = score(indicators=[indicator], ssp_doc=_ssp(), poam_doc=_poam())
        assert len(result.indicators) == 1
        ind = result.indicators[0]
        assert ind.status == INDICATOR_IN_PROGRESS
        assert len(ind.controls) == 1
        c = ind.controls[0]
        assert c.status == CONTROL_OPEN
        assert "POAM-001" in c.poam_item_ids

    def test_not_applicable_control_counts_as_passing(self):
        # ac-11 is "not-applicable" in the Samsite SSP per earlier inspection.
        indicator = {
            "code": "KSI-TEST-AC11",
            "name": "AC-11 only",
            "classes": ["c"],
            "controls": ["ac-11"],
        }
        result = score(indicators=[indicator], ssp_doc=_ssp(), poam_doc=_poam())
        ind = result.indicators[0]
        assert ind.controls[0].status == CONTROL_NA
        assert ind.status == INDICATOR_PASSING

    def test_control_missing_from_ssp_is_unmapped_gap(self):
        indicator = {
            "code": "KSI-TEST-FAKE",
            "name": "Fake control",
            "classes": ["c"],
            "controls": ["xyz-99"],
        }
        result = score(indicators=[indicator], ssp_doc=_ssp(), poam_doc=_poam())
        ind = result.indicators[0]
        assert ind.controls[0].status == CONTROL_UNMAPPED
        assert ind.status == INDICATOR_GAP

    def test_mixed_indicator_takes_worst_case_status(self):
        # Mixing AC-2 (open POA&M) + AC-1 (implemented) → indicator in-progress.
        indicator = {
            "code": "KSI-TEST-MIX",
            "name": "Mixed",
            "classes": ["c"],
            "controls": ["ac-1", "ac-2"],
        }
        result = score(indicators=[indicator], ssp_doc=_ssp(), poam_doc=_poam())
        ind = result.indicators[0]
        statuses = {c.control_id: c.status for c in ind.controls}
        assert statuses["ac-1"] == CONTROL_PASS
        assert statuses["ac-2"] == CONTROL_OPEN
        assert ind.status == INDICATOR_IN_PROGRESS

    def test_all_implemented_passes(self):
        # ac-1 and ac-3 are both implemented (no POA&M coverage in Samsite).
        indicator = {
            "code": "KSI-TEST-ALL",
            "name": "All passing",
            "classes": ["c"],
            "controls": ["ac-1", "ac-3"],
        }
        result = score(indicators=[indicator], ssp_doc=_ssp(), poam_doc=_poam())
        ind = result.indicators[0]
        assert all(c.status == CONTROL_PASS for c in ind.controls)
        assert ind.status == INDICATOR_PASSING


class TestClassFiltering:
    def test_excludes_indicators_outside_system_class(self):
        indicators = [
            {"code": "KSI-A-ONE", "name": "A only", "classes": ["a"], "controls": ["ac-1"]},
            {"code": "KSI-C-ONE", "name": "C only", "classes": ["c"], "controls": ["ac-1"]},
            {"code": "KSI-D-ONE", "name": "D only", "classes": ["d"], "controls": ["ac-1"]},
            {"code": "KSI-BC-ONE", "name": "B+C", "classes": ["b", "c"], "controls": ["ac-1"]},
        ]
        result = score(indicators=indicators, ssp_doc=_ssp(), poam_doc=_poam())
        codes = [i.code for i in result.indicators]
        assert "KSI-C-ONE" in codes
        assert "KSI-BC-ONE" in codes
        assert "KSI-A-ONE" not in codes
        assert "KSI-D-ONE" not in codes
        assert result.excluded_class_mismatch == 2

    def test_no_class_signal_means_no_filtering(self):
        # No SSP, no override → all indicators scored regardless of class.
        indicators = [
            {"code": "KSI-A-ONE", "name": "A only", "classes": ["a"], "controls": ["ac-1"]},
            {"code": "KSI-D-ONE", "name": "D only", "classes": ["d"], "controls": ["ac-1"]},
        ]
        result = score(indicators=indicators, ssp_doc=None, poam_doc=None)
        assert len(result.indicators) == 2
        assert result.excluded_class_mismatch == 0


class TestClassVariants:
    def test_class_variants_override_base_controls(self):
        indicator = {
            "code": "KSI-TEST-VAR",
            "name": "Variant test",
            "classes": ["c", "d"],
            "controls": ["ac-1"],  # base — used if no variant
            "class_variants": {
                "c": {"controls": ["ac-1", "ac-2"]},  # Class C also needs ac-2
                "d": {"controls": ["ac-1", "ac-2", "ac-3"]},
            },
        }
        result = score(indicators=[indicator], ssp_doc=_ssp(), poam_doc=_poam())
        ind = result.indicators[0]
        control_ids = [c.control_id for c in ind.controls]
        assert control_ids == ["ac-1", "ac-2"]  # Class C variant


class TestGrouping:
    def test_group_by_theme_preserves_order(self):
        indicators = [
            {"code": "KSI-CMT-LMC", "name": "Logging Changes", "classes": ["c"], "controls": ["ac-1"]},
            {"code": "KSI-IAM-MFA", "name": "MFA", "classes": ["c"], "controls": ["ac-1"]},
            {"code": "KSI-CMT-VER", "name": "Verifying Changes", "classes": ["c"], "controls": ["ac-1"]},
        ]
        result = score(indicators=indicators, ssp_doc=_ssp(), poam_doc=_poam())
        themed = group_by_theme(result)
        assert {g["theme_code"] for g in themed} == {"KSI-CMT", "KSI-IAM"}
        cmt = next(g for g in themed if g["theme_code"] == "KSI-CMT")
        assert [i.code for i in cmt["indicators"]] == ["KSI-CMT-LMC", "KSI-CMT-VER"]


class TestTotals:
    def test_totals_count_by_status(self):
        indicators = [
            {"code": "KSI-T1", "name": "p1", "classes": ["c"], "controls": ["ac-1"]},
            {"code": "KSI-T2", "name": "p2", "classes": ["c"], "controls": ["ac-1"]},
            {"code": "KSI-T3", "name": "g1", "classes": ["c"], "controls": ["zz-99"]},
            {"code": "KSI-T4", "name": "o1", "classes": ["c"], "controls": ["ac-2"]},
        ]
        result = score(indicators=indicators, ssp_doc=_ssp(), poam_doc=_poam())
        assert result.totals.get(INDICATOR_PASSING) == 2
        assert result.totals.get(INDICATOR_GAP) == 1
        assert result.totals.get(INDICATOR_IN_PROGRESS) == 1
