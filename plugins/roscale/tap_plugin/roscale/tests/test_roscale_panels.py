"""Panel context-building tests.

The panel resolver calls Gryphon, which needs Django/DB state. These tests
exercise the pure pieces — section extractors, headline stats, provenance,
and the build_context happy/sad paths with a mocked artifact resolution —
so they run without an INSTALLED_APPS setup.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from tap_plugin.roscale.panels._common import (
    build_provenance,
    poam_headline_stats,
    poam_items,
    poam_metadata,
    ssp_components,
    ssp_headline_stats,
    ssp_implemented_requirements,
    ssp_implemented_requirements_by_family,
    ssp_metadata,
    ssp_self_attestation_signal,
    ssp_system_overview,
)

from tap_web.panels.entity_resolution import EntityResolution

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, "rb") as fh:
        return json.load(fh)


class _FakePanel:
    def __init__(self, config: dict | None = None):
        self.config = config or {}


class _FakeRequest:
    def __init__(self, params: dict | None = None):
        self.GET = params or {}


def _fake_node(content, **extras) -> dict:
    """Mimic Gryphon's `layer=extended` envelope: spine fields flat at the top,
    per-model fields nested under `data`."""
    data = {
        "entity_id": "ent-xyz",
        "name": "samsite-oscal-ssp",
        "kind": "oscal_ssp",
        "source_url": "https://samsite.unified-systems.com/.well-known/oscal-ssp.json",
        "fetched_at": "2026-05-26T11:00:00Z",
        "content_type": "application/oscal+json",
        "size_bytes": 762161,
        "content": content,
        "signature_verified": True,
        "signed_by": "https://github.com/notgeorge/samsite/...",
        "rekor_log_index": "12345678",
        "verified_at": "2026-05-26T11:00:01Z",
        **extras,
    }
    return {
        "entity_id": "ent-xyz",
        "entity_type": "compliance_artifact",
        "name": data["name"],
        "dimensions": {},
        "data": data,
    }


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestBuildProvenance:
    def test_provenance_keys_present(self):
        prov = build_provenance(_fake_node(content={"system-security-plan": {}}))
        for key in ("source_url", "fetched_at", "signature_verified", "signed_by", "rekor_log_index", "verified_at"):
            assert key in prov

    def test_signature_verified_value(self):
        prov = build_provenance(_fake_node(content={"system-security-plan": {}}, signature_verified=False))
        assert prov["signature_verified"] is False


# ---------------------------------------------------------------------------
# SSP extractors against the live Samsite SSP fixture
# ---------------------------------------------------------------------------


class TestSspExtractors:
    @pytest.fixture
    def ssp(self) -> dict:
        return _load("samsite_oscal_ssp.json")

    def test_metadata(self, ssp):
        md = ssp_metadata(ssp)
        assert md["oscal_version"]
        assert md["title"]
        assert md["last_modified"]

    def test_system_overview(self, ssp):
        so = ssp_system_overview(ssp)
        assert so["system_name"]
        assert "confidentiality" in so

    def test_implemented_requirements_nonempty(self, ssp):
        reqs = ssp_implemented_requirements(ssp)
        assert len(reqs) > 0
        assert all("control_id" in r for r in reqs)
        assert all("family_label" in r for r in reqs)

    def test_requirements_by_family_groups(self, ssp):
        reqs = ssp_implemented_requirements(ssp)
        by_fam = ssp_implemented_requirements_by_family(reqs)
        assert len(by_fam) > 0
        assert sum(g["count"] for g in by_fam) == len(reqs)
        # Each family group's labels should match
        for g in by_fam:
            assert all(r["family_label"] == g["family"] for r in g["requirements"])

    def test_components_listed(self, ssp):
        comps = ssp_components(ssp)
        assert len(comps) >= 1
        assert all("title" in c for c in comps)

    def test_headline_stats_shape(self, ssp):
        reqs = ssp_implemented_requirements(ssp)
        stats = ssp_headline_stats(ssp, reqs)
        assert stats["total_controls"] == len(reqs)
        assert "family_counts" in stats
        assert "implementation_status_counts" in stats

    def test_self_attestation_signal_returns_struct(self, ssp):
        sig = ssp_self_attestation_signal(ssp)
        assert "indicators" in sig
        assert "matches" in sig


# ---------------------------------------------------------------------------
# POA&M extractors against the live Samsite POA&M fixture
# ---------------------------------------------------------------------------


class TestPoamExtractors:
    @pytest.fixture
    def poam(self) -> dict:
        return _load("samsite_oscal_poam.json")

    def test_metadata(self, poam):
        md = poam_metadata(poam)
        assert md["oscal_version"]
        assert md["title"]

    def test_items_nonempty(self, poam):
        items = poam_items(poam)
        assert len(items) > 0
        assert all("uuid" in it for it in items)

    def test_headline_stats(self, poam):
        items = poam_items(poam)
        stats = poam_headline_stats(items)
        assert stats["total"] == len(items)
        # Samsite POA&M has 18 items, 2 open + 16 risk-accepted per the spec
        assert stats["open_count"] + stats["risk_accepted_count"] <= stats["total"]


# ---------------------------------------------------------------------------
# build_context — happy path + error states (mock resolve_entity)
# ---------------------------------------------------------------------------


class TestSspBuildContext:
    def test_happy_path_against_samsite_ssp(self):
        from tap_plugin.roscale.panels import oscal_workbench

        with patch("tap_plugin.roscale.panels.oscal_workbench.resolve_entity") as mock_resolve:
            mock_resolve.return_value = EntityResolution(
                entity_id="ent-xyz",
                var_name="oscal_ssp_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_ssp.json")),
                error=None,
            )
            ctx = oscal_workbench.build_context(_FakePanel(), _FakeRequest({"oscal_ssp_artifact_entity_id": "ent-xyz"}))

        assert ctx["error_phase"] is None
        assert ctx["error_message"] is None
        assert ctx["metadata"]["title"]
        assert ctx["validation"]["schema_ok"] is True
        assert ctx["headline_stats"]["total_controls"] > 0
        assert ctx["requirements_by_family"]
        assert ctx["raw_json"]

    def test_no_entity_id_is_polished_error(self):
        from tap_plugin.roscale.panels import oscal_workbench

        ctx = oscal_workbench.build_context(_FakePanel(), _FakeRequest({}))
        assert ctx["error_phase"] == "load"
        assert "oscal_ssp_artifact_entity_id" in ctx["error_message"]

    def test_wrong_root_returns_root_detect_error(self):
        from tap_plugin.roscale.panels import oscal_workbench

        with patch("tap_plugin.roscale.panels.oscal_workbench.resolve_entity") as mock_resolve:
            mock_resolve.return_value = EntityResolution(
                entity_id="ent-xyz",
                var_name="oscal_ssp_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_poam.json")),
                error=None,
            )
            ctx = oscal_workbench.build_context(_FakePanel(), _FakeRequest({"oscal_ssp_artifact_entity_id": "ent-xyz"}))

        assert ctx["error_phase"] == "root-detect"
        # JSON fallback still available even when root is wrong
        assert ctx["raw_json"]


class TestPoamBuildContext:
    def test_happy_path_against_samsite_poam(self):
        from tap_plugin.roscale.panels import oscal_poam_workbench

        with patch("tap_plugin.roscale.panels.oscal_poam_workbench.resolve_entity") as mock_resolve:
            mock_resolve.return_value = EntityResolution(
                entity_id="ent-xyz",
                var_name="oscal_poam_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_poam.json"), kind="oscal_poam"),
                error=None,
            )
            ctx = oscal_poam_workbench.build_context(
                _FakePanel(), _FakeRequest({"oscal_poam_artifact_entity_id": "ent-xyz"})
            )

        assert ctx["error_phase"] is None
        assert ctx["headline_stats"]["total"] > 0
        assert ctx["items"]
        assert ctx["validation"]["schema_ok"] is True

    def test_no_entity_id_is_polished_error(self):
        from tap_plugin.roscale.panels import oscal_poam_workbench

        ctx = oscal_poam_workbench.build_context(_FakePanel(), _FakeRequest({}))
        assert ctx["error_phase"] == "load"
        assert "oscal_poam_artifact_entity_id" in ctx["error_message"]


# ---------------------------------------------------------------------------
# build_context — fallback path (no URL var, fallback configured)
# ---------------------------------------------------------------------------
#
# Direct tests of the canonical resolver live in
# tap_web/tests/test_panel_entity_resolution.py — those tests cover URL-wins /
# fallback-fires / no-URL-no-fallback / empty / ambiguous / transient paths
# against EntityResolution. The tests below verify that the panel's
# build_context correctly propagates resolution outcome into template context.


class TestPanelBuildContextWithFallback:
    SSP_FALLBACK_DESCRIPTION = "Latest oscal_ssp compliance artifact by fetched_at."
    POAM_FALLBACK_DESCRIPTION = "Latest oscal_poam compliance artifact by fetched_at."

    def test_ssp_build_context_propagates_fallback_flag(self):
        from tap_plugin.roscale.panels import oscal_workbench

        with patch("tap_plugin.roscale.panels.oscal_workbench.resolve_entity") as mock_resolve:
            mock_resolve.return_value = EntityResolution(
                entity_id="ent-latest",
                var_name="oscal_ssp_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_ssp.json")),
                error=None,
                used_fallback=True,
                fallback_description=self.SSP_FALLBACK_DESCRIPTION,
                fallback_count=1,
            )
            ctx = oscal_workbench.build_context(_FakePanel(), _FakeRequest({}))

        assert ctx["used_fallback"] is True
        assert ctx["fallback_description"] == self.SSP_FALLBACK_DESCRIPTION
        assert ctx["error_phase"] is None
        assert ctx["metadata"]["title"]

    def test_poam_build_context_propagates_fallback_flag(self):
        from tap_plugin.roscale.panels import oscal_poam_workbench

        with patch("tap_plugin.roscale.panels.oscal_poam_workbench.resolve_entity") as mock_resolve:
            mock_resolve.return_value = EntityResolution(
                entity_id="ent-latest",
                var_name="oscal_poam_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_poam.json"), kind="oscal_poam"),
                error=None,
                used_fallback=True,
                fallback_description=self.POAM_FALLBACK_DESCRIPTION,
                fallback_count=1,
            )
            ctx = oscal_poam_workbench.build_context(_FakePanel(), _FakeRequest({}))

        assert ctx["used_fallback"] is True
        assert ctx["fallback_description"] == self.POAM_FALLBACK_DESCRIPTION
        assert ctx["error_phase"] is None
        assert ctx["items"]
