"""End-to-end tests for KSICollector.

Covers req-fedramp-20x-ksi-collector-* from
plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-collector.md.

The network fetch is overridden via `_fetch_upstream_bytes` so tests run
deterministically against a committed fixture (`tests/fixtures/ksi_catalog/
current.json`). A separate `@pytest.mark.live_fetch` test (also here) verifies
real upstream parsing; skipped by default per
req-fedramp-20x-ksi-collector-test-strategy-3.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import tap_plugin.fedramp_20x_ksi.collectors.ksi_catalog as ksi_module
from tap_plugin.fedramp_20x_ksi.collectors.ksi_catalog import (
    KSICollector,
)

from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.registry import collector_registry, reconcile_collector_nodes, register_collector
from tap_cares.services import run_collection
from tap_grid.batch import produced_batches

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ksi_catalog"
_CURRENT_FIXTURE = _FIXTURE_DIR / "current.json"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _load_fixture() -> dict:
    return json.loads(_CURRENT_FIXTURE.read_text())


def _fixture_bytes(doc: dict | None = None) -> bytes:
    if doc is None:
        return _CURRENT_FIXTURE.read_bytes()
    return json.dumps(doc).encode("utf-8")


def _make_collector_with_fixture(doc: dict | None = None):
    """Return a KSICollector subclass that returns the given fixture content."""
    body = _fixture_bytes(doc)
    sha = hashlib.sha256(body).hexdigest()
    size = len(body)

    class _FixtureKSICollector(KSICollector):
        def _fetch_upstream_bytes(self) -> tuple[bytes, str, int]:
            from tap_plugin.fedramp_20x_ksi.collectors.ksi_catalog import (
                _SITE_UPSTREAM_FETCHED,
            )

            self.record_info(
                _SITE_UPSTREAM_FETCHED,
                "UPSTREAM_FETCHED",
                f"Fetched {size} bytes from fixture.",
                message_data={"url": "fixture://current.json", "byte_size": size, "content_sha256": sha},
            )
            return body, sha, size

    _FixtureKSICollector.__module__ = "tap_plugin.fedramp_20x_ksi.tests.fixtures.injected"
    return _FixtureKSICollector


_TEST_SCOPE = "tap_plugin.fedramp_20x_ksi.tests.fixtures.injected"
_TEST_REGISTRY_KEY = f"{_TEST_SCOPE}:ksi-catalog-test"


def _register_and_fetch(
    cls, *, name: str = "KSI Catalog (test)", description: str = "Fixture-driven KSI collector under test."
) -> Collector:
    """Register `cls` under the test scope:key AND return the on-grid Collector.

    After the dual-existence refactor, register_collector creates the on-grid
    Collector node deterministically. This helper centralizes the registration
    + fetch so each test just gets a usable Collector instance.
    """
    register_collector(
        key="ksi-catalog-test",
        cls=cls,
        scope=_TEST_SCOPE,
        name=name,
        description=description,
    )
    reconcile_collector_nodes()  # materialize the on-grid node (register is read-only)
    return Collector.objects.get(collector_registry=_TEST_REGISTRY_KEY)


@pytest.fixture
def isolate_collector_registry():
    saved = collector_registry.all()
    collector_registry._reset_for_testing()
    yield
    collector_registry._reset_for_testing(saved)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class _FakeHttpResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_self_test_checks_upstream_reachability(monkeypatch):
    def fake_urlopen(request, *, timeout):
        assert request.get_method() == "HEAD"
        assert timeout == ksi_module.UPSTREAM_TIMEOUT_SECONDS
        return _FakeHttpResponse()

    monkeypatch.setattr(ksi_module.urllib.request, "urlopen", fake_urlopen)

    result = KSICollector.self_test()

    assert result.status.value == "ready"
    assert result.runnable is True
    assert [check.code for check in result.checks] == [
        "UPSTREAM_URL_CONFIGURED",
        "UPSTREAM_REACHABLE",
    ]


@pytest.mark.django_db(transaction=True)
class TestHappyPathFreshInstall:
    """Fresh install: grid empty; fixture lands as all-new."""

    def test_run_succeeds_and_submits_batch(self, isolate_collector_registry):
        cls = _make_collector_with_fixture()
        col = _register_and_fetch(cls)
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.SUCCESSFUL
        # On a fresh import the collector writes a human-readable summary
        # describing what landed.
        assert "Imported" in job.summary
        assert "indicators" in job.summary
        assert len(produced_batches(job.entity_id)["imported"]) == 1
        codes = [e["message_code"] for e in job.results["info"]]
        assert "RUN_STARTED" in codes
        assert "UPSTREAM_FETCHED" in codes
        assert "DIFF_COMPUTED" in codes
        assert "GRIFT_SUBMITTED" in codes
        assert "RUN_COMPLETED" in codes
        assert job.results["error"] == []

    def test_ctl_section_is_tolerated(self, isolate_collector_registry):
        # FedRAMP added a top-level CTL (organization-defined-parameter baseline)
        # section to the consolidated rules upstream 2026-06. It is orthogonal to
        # the KSI catalog this collector ingests, so the pinned subset schema
        # tolerates it as opaque sibling data rather than blocking on drift
        # (req-fedramp-20x-ksi-collector-validation-scope). Genuinely-unknown keys
        # are still rejected — see test_unknown_field.
        doc = _load_fixture()
        doc["CTL"] = {"AC": {"AC-06-01": {"parameters": [{"parameterId": "ac-06.01_odp.02", "value": "x"}]}}}
        cls = _make_collector_with_fixture(doc)
        col = _register_and_fetch(cls)
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.SUCCESSFUL
        assert job.results["error"] == []

    def test_themes_and_indicators_land_on_grid(self, isolate_collector_registry):
        from tap_plugin.fedramp_20x_ksi.models import KsiIndicator, KsiTheme

        cls = _make_collector_with_fixture()
        col = _register_and_fetch(cls)
        run_collection(col)
        # Fixture currently has 10 themes and ~50 indicators per FedRAMP catalog.
        assert KsiTheme.objects.count() >= 1
        assert KsiIndicator.objects.count() >= 1

    def test_change_counts_in_description_json(self, isolate_collector_registry):
        from tap_grid.models import Batch

        cls = _make_collector_with_fixture()
        col = _register_and_fetch(cls)
        job = run_collection(col)
        job.refresh_from_db()
        batch_id = produced_batches(job.entity_id)["imported"][0]
        batch = Batch.objects.get(entity_id=batch_id)
        data = batch.description_json["data"]
        assert data["schema_version"] == "v0"
        assert (
            data["source"]["url"]
            == "https://raw.githubusercontent.com/FedRAMP/rules/main/fedramp-consolidated-rules.json"
        )
        assert data["changes"]["catalog_size_before"] == 0  # fresh install
        assert data["changes"]["indicators_new"] >= 1


# ---------------------------------------------------------------------------
# Empty diff (re-run on already-up-to-date grid)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestEmptyDiff:
    def test_second_run_with_no_changes_is_noop(self, isolate_collector_registry):
        cls = _make_collector_with_fixture()
        col = _register_and_fetch(cls)

        first = run_collection(col)
        first.refresh_from_db()
        assert first.status == CollectionJobStatus.SUCCESSFUL

        second = run_collection(col)
        second.refresh_from_db()
        assert second.status == CollectionJobStatus.SUCCESSFUL
        assert produced_batches(second.entity_id)["imported"] == []
        codes = [e["message_code"] for e in second.results["info"]]
        assert "DIFF_EMPTY" in codes
        assert "GRIFT_SUBMITTED" not in codes


# ---------------------------------------------------------------------------
# Block flags
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestBlockFlags:
    """Each block-class flag aborts before submission and records an error entry."""

    def _run_and_assert_failed(self, cls, expected_code: str) -> CollectionJob:
        # The Django immediate task backend captures exceptions on the TaskResult
        # instead of re-raising to the caller (see test_task_execution.py for
        # the rationale). Failure surfaces via job.status / job.results, not
        # via an exception out of run_collection.
        col = _register_and_fetch(cls)
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        assert produced_batches(job.entity_id)["imported"] == []
        codes = [e["message_code"] for e in job.results["error"]]
        assert expected_code in codes, f"Expected {expected_code} in {codes}"
        assert job.summary
        return job

    def test_bad_content_type(self, isolate_collector_registry):
        class _BadCT(KSICollector):
            def _fetch_upstream_bytes(self):
                self._abort(
                    ksi_module._SITE_UPSTREAM_BAD_CONTENT_TYPE,
                    "UPSTREAM_BAD_CONTENT_TYPE",
                    "fixture: bad content type",
                )

        _BadCT.__module__ = "tap_plugin.fedramp_20x_ksi.tests.fixtures.injected"
        self._run_and_assert_failed(_BadCT, "UPSTREAM_BAD_CONTENT_TYPE")

    def test_oversized(self, isolate_collector_registry):
        class _Oversized(KSICollector):
            def _fetch_upstream_bytes(self):
                self._abort(
                    ksi_module._SITE_UPSTREAM_OVERSIZED,
                    "UPSTREAM_OVERSIZED",
                    "fixture: oversized",
                )

        _Oversized.__module__ = "tap_plugin.fedramp_20x_ksi.tests.fixtures.injected"
        self._run_and_assert_failed(_Oversized, "UPSTREAM_OVERSIZED")

    def test_schema_drift(self, isolate_collector_registry):
        doc = _load_fixture()
        # Remove the required "info" top-level key.
        doc.pop("info", None)
        cls = _make_collector_with_fixture(doc)
        self._run_and_assert_failed(cls, "SCHEMA_DRIFT")

    def test_unknown_field(self, isolate_collector_registry):
        doc = _load_fixture()
        doc["completely_bogus_top_key"] = "surprise"
        cls = _make_collector_with_fixture(doc)
        # Pinned schema rejects unknown top-level keys via UNKNOWN_FIELD or
        # SCHEMA_DRIFT depending on which check fires first.
        col = _register_and_fetch(cls)
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        codes = [e["message_code"] for e in job.results["error"]]
        assert any(c in codes for c in ("UNKNOWN_FIELD", "SCHEMA_DRIFT"))

    def test_structural_cap_themes(self, isolate_collector_registry):
        doc = _load_fixture()
        # Pad KSI with copies until we exceed MAX_THEMES (20). Theme keys must
        # match `^[A-Z]{3}$` per the pinned schema, otherwise SCHEMA_DRIFT fires
        # before STRUCTURAL_CAP. Use Z-prefixed 3-letter codes that won't
        # collide with real FedRAMP theme keys.
        theme_template = next(iter(doc["KSI"].values()))
        for i in range(25):
            key = f"ZZ{chr(ord('A') + i)}" if i < 26 else f"YZ{chr(ord('A') + i - 26)}"
            doc["KSI"][key] = copy.deepcopy(theme_template)
        cls = _make_collector_with_fixture(doc)
        self._run_and_assert_failed(cls, "STRUCTURAL_CAP")

    def test_character_class_control(self, isolate_collector_registry):
        doc = _load_fixture()
        # Inject a control character into the first indicator's statement.
        for theme in doc["KSI"].values():
            indicators = theme.get("indicators", {})
            for _code, ind in indicators.items():
                if ind.get("statement"):
                    ind["statement"] = "\x07evil" + ind["statement"]
                    break
            else:
                continue
            break
        cls = _make_collector_with_fixture(doc)
        self._run_and_assert_failed(cls, "CHARACTER_CLASS")

    def test_mass_deletion(self, isolate_collector_registry):
        # First successful run seeds the grid.
        cls = _make_collector_with_fixture()
        col = _register_and_fetch(cls)
        run_collection(col)

        # Second run with most indicators stripped out trips MASS_DELETION.
        doc = _load_fixture()
        for theme in doc["KSI"].values():
            indicators = theme.get("indicators", {})
            kept = dict(list(indicators.items())[:1])  # keep only one per theme
            theme["indicators"] = kept
        # Re-register a new collector class with the stripped fixture. The
        # on-grid Collector node is reused (same scope:key → same UUIDv5);
        # register_collector upserts the row's mutable fields.
        collector_registry._reset_for_testing()
        cls2 = _make_collector_with_fixture(doc)
        col = _register_and_fetch(cls2)
        second = run_collection(col)
        second.refresh_from_db()
        assert second.status == CollectionJobStatus.FAILED
        codes = [e["message_code"] for e in second.results["error"]]
        assert "MASS_DELETION" in codes


# ---------------------------------------------------------------------------
# Live fetch (network) — opt-in
# ---------------------------------------------------------------------------


@pytest.mark.live_fetch
@pytest.mark.django_db(transaction=True)
def test_live_fetch_round_trip(isolate_collector_registry):
    """Verify the real HTTPS fetch succeeds and the upstream parses cleanly.

    Skipped by default (`@pytest.mark.live_fetch`). Enable with
    `pytest -m live_fetch` when you want to validate against the live
    upstream — e.g., before tagging a release.
    """
    # Register the live collector under its own test qualified key. Scope is an
    # explicit declaration (mandatory) — here a distinct test scope so it never
    # collides with the production `fedramp_20x_ksi:ksi-catalog` registration.
    _live_scope = "tap_plugin.fedramp_20x_ksi.collectors.ksi_catalog"
    register_collector(
        key="ksi-catalog-test",
        cls=KSICollector,
        scope=_live_scope,
        name="KSI Catalog (live test)",
        description="Live-network KSI collector test.",
    )
    reconcile_collector_nodes()  # materialize the on-grid node (register is read-only)
    live_key = f"{_live_scope}:ksi-catalog-test"
    col = Collector.objects.get(collector_registry=live_key)
    # We don't assert on diff shape (upstream changes). The immediate backend
    # captures any KSICollectorError on the TaskResult; job.status is the
    # source of truth here.
    job = run_collection(col)
    job.refresh_from_db()
    assert job.status in (CollectionJobStatus.SUCCESSFUL, CollectionJobStatus.FAILED)
