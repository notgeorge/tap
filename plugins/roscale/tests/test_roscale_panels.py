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

from plugins.roscale.panels import _common
from plugins.roscale.panels._common import (
    ArtifactResolution,
    build_provenance,
    poam_headline_stats,
    poam_items,
    poam_metadata,
    resolve_artifact,
    ssp_components,
    ssp_headline_stats,
    ssp_implemented_requirements,
    ssp_implemented_requirements_by_family,
    ssp_metadata,
    ssp_self_attestation_signal,
    ssp_system_overview,
)

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
# build_context — happy path + error states (mock resolve_artifact)
# ---------------------------------------------------------------------------


class TestSspBuildContext:
    def test_happy_path_against_samsite_ssp(self):
        from plugins.roscale.panels import oscal_workbench

        with patch("plugins.roscale.panels.oscal_workbench.resolve_artifact") as mock_resolve:
            mock_resolve.return_value = ArtifactResolution(
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
        from plugins.roscale.panels import oscal_workbench

        ctx = oscal_workbench.build_context(_FakePanel(), _FakeRequest({}))
        assert ctx["error_phase"] == "load"
        assert "oscal_ssp_artifact_entity_id" in ctx["error_message"]

    def test_wrong_root_returns_root_detect_error(self):
        from plugins.roscale.panels import oscal_workbench

        with patch("plugins.roscale.panels.oscal_workbench.resolve_artifact") as mock_resolve:
            mock_resolve.return_value = ArtifactResolution(
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
        from plugins.roscale.panels import oscal_poam_workbench

        with patch("plugins.roscale.panels.oscal_poam_workbench.resolve_artifact") as mock_resolve:
            mock_resolve.return_value = ArtifactResolution(
                entity_id="ent-xyz",
                var_name="oscal_poam_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_poam.json"), kind="oscal_poam"),
                error=None,
            )
            ctx = oscal_poam_workbench.build_context(_FakePanel(), _FakeRequest({"oscal_poam_artifact_entity_id": "ent-xyz"}))

        assert ctx["error_phase"] is None
        assert ctx["headline_stats"]["total"] > 0
        assert ctx["items"]
        assert ctx["validation"]["schema_ok"] is True

    def test_no_entity_id_is_polished_error(self):
        from plugins.roscale.panels import oscal_poam_workbench

        ctx = oscal_poam_workbench.build_context(_FakePanel(), _FakeRequest({}))
        assert ctx["error_phase"] == "load"
        assert "oscal_poam_artifact_entity_id" in ctx["error_message"]


# ---------------------------------------------------------------------------
# resolve_artifact — fallback path (no URL var, config.fallback.kind set)
# ---------------------------------------------------------------------------


class TestResolveArtifactFallback:
    def test_explicit_entity_id_wins_over_fallback(self):
        """When both URL var and fallback are present, URL wins; fallback unused."""
        panel = _FakePanel({"artifact_entity_id_var": "var", "fallback": {"kind": "oscal_ssp"}})
        node = _fake_node(content={"system-security-plan": {}})

        with patch("plugins.roscale.panels._common._lookup_by_entity_id", return_value=node) as by_id, \
             patch("plugins.roscale.panels._common._lookup_latest_by_kind") as by_kind:
            result = resolve_artifact(panel, _FakeRequest({"var": "ent-xyz"}), "default-var")

        assert result.ok
        assert result.used_fallback is False
        assert by_id.called
        assert not by_kind.called

    def test_fallback_used_when_url_var_empty(self):
        panel = _FakePanel({"artifact_entity_id_var": "var", "fallback": {"kind": "oscal_ssp"}})
        node = _fake_node(content={"system-security-plan": {}})

        with patch("plugins.roscale.panels._common._lookup_latest_by_kind", return_value=node) as by_kind:
            result = resolve_artifact(panel, _FakeRequest({}), "default-var")

        assert result.ok
        assert result.used_fallback is True
        assert result.fallback_kind == "oscal_ssp"
        by_kind.assert_called_once_with("oscal_ssp")

    def test_no_fallback_no_url_var_returns_no_artifact_error(self):
        panel = _FakePanel({"artifact_entity_id_var": "var"})

        with patch("plugins.roscale.panels._common._lookup_by_entity_id") as by_id, \
             patch("plugins.roscale.panels._common._lookup_latest_by_kind") as by_kind:
            result = resolve_artifact(panel, _FakeRequest({}), "default-var")

        assert not result.ok
        assert result.used_fallback is False
        assert "No artifact specified" in result.error
        assert not by_id.called
        assert not by_kind.called

    def test_fallback_kind_with_no_matches_returns_polished_error(self):
        panel = _FakePanel({"artifact_entity_id_var": "var", "fallback": {"kind": "oscal_ssp"}})

        with patch("plugins.roscale.panels._common._lookup_latest_by_kind", return_value=None):
            result = resolve_artifact(panel, _FakeRequest({}), "default-var")

        assert not result.ok
        assert result.fallback_kind == "oscal_ssp"
        assert "kind 'oscal_ssp'" in result.error

    def test_lookup_latest_by_kind_sorts_by_fetched_at_desc(self):
        """The latest-by-kind helper picks the highest fetched_at value."""
        # Flat envelope: spine fields at top, per-model fields under `data`.
        nodes = [
            {"entity_id": "a", "data": {"fetched_at": "2026-05-24T10:00:00Z"}},
            {"entity_id": "b", "data": {"fetched_at": "2026-05-26T10:00:00Z"}},
            {"entity_id": "c", "data": {"fetched_at": "2026-05-25T10:00:00Z"}},
            {"entity_id": "d", "data": {"fetched_at": ""}},  # empty sorts last
        ]
        fake_result = {"results": {"nodes": nodes}}

        # `_lookup_latest_by_kind` imports Search + execute_search inside the
        # function body, so patches target the source modules.
        with patch("tap_grid.search.execute_search", return_value=fake_result), \
             patch("tap_grid.models.Search"):
            latest = _common._lookup_latest_by_kind("oscal_ssp")

        assert latest["entity_id"] == "b"


class TestPanelBuildContextWithFallback:
    def test_ssp_build_context_propagates_fallback_flag(self):
        from plugins.roscale.panels import oscal_workbench

        with patch("plugins.roscale.panels.oscal_workbench.resolve_artifact") as mock_resolve:
            mock_resolve.return_value = ArtifactResolution(
                entity_id="ent-latest",
                var_name="oscal_ssp_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_ssp.json")),
                error=None,
                used_fallback=True,
                fallback_kind="oscal_ssp",
            )
            ctx = oscal_workbench.build_context(_FakePanel(), _FakeRequest({}))

        assert ctx["used_fallback"] is True
        assert ctx["fallback_kind"] == "oscal_ssp"
        assert ctx["error_phase"] is None
        assert ctx["metadata"]["title"]

    def test_poam_build_context_propagates_fallback_flag(self):
        from plugins.roscale.panels import oscal_poam_workbench

        with patch("plugins.roscale.panels.oscal_poam_workbench.resolve_artifact") as mock_resolve:
            mock_resolve.return_value = ArtifactResolution(
                entity_id="ent-latest",
                var_name="oscal_poam_artifact_entity_id",
                node=_fake_node(content=_load("samsite_oscal_poam.json"), kind="oscal_poam"),
                error=None,
                used_fallback=True,
                fallback_kind="oscal_poam",
            )
            ctx = oscal_poam_workbench.build_context(_FakePanel(), _FakeRequest({}))

        assert ctx["used_fallback"] is True
        assert ctx["fallback_kind"] == "oscal_poam"
        assert ctx["error_phase"] is None
        assert ctx["items"]
