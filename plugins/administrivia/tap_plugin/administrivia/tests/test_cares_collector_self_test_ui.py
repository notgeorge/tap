"""Administrivia CARES self-test UI tests (async self_test_only contract).

The Self-test button no longer runs a synchronous self-test and renders the
result inline. It POSTs `action=self_test`, which goes through
`run_collection(run_mode="self_test_only")` (the sole CollectionJob creator).
The table shows a queued flash; the detail page renders readiness from the
latest persisted `CollectionJob.self_test` and HTMX-polls that block.

Spec: tap_cares/specs/spec-tap-cares-administrivia.md
  req-tap-cares-administrivia-collector-readiness-{1,7,8,9,10}
  tap_cares/specs/spec-tap-cares-collector.md req-tap-cares-collector-self-test-16
"""

from __future__ import annotations

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from tap_plugin.administrivia.tap_cares.panels.collector_detail import (
    CollectorDetailPanelType,
)
from tap_plugin.administrivia.tap_cares.panels.collector_table import (
    CollectorTablePanelType,
)

from tap_cares.collectors import (
    CollectorBase,
    CollectorReadinessStatus,
    CollectorSelfTestResult,
    check_fail,
)
from tap_cares.models import CollectionJob, CollectionJobRunMode, Collector
from tap_cares.registry import collector_registry, reconcile_collector_nodes, register_collector
from tap_cares.services import run_collection
from tap_web.models import Panel


class UnconfiguredCollector(CollectorBase):
    @classmethod
    def self_test(cls) -> CollectorSelfTestResult:
        return CollectorSelfTestResult.from_checks(
            [
                check_fail(
                    "CONFIG_PRESENT",
                    "The test collector is not configured.",
                    readiness_status=CollectorReadinessStatus.UNCONFIGURED,
                )
            ],
            summary="The test collector is not configured yet.",
        )

    def run(self) -> None:
        return None


@pytest.fixture
def isolate_collector_registry():
    saved = collector_registry.all()
    collector_registry._reset_for_testing()
    yield
    collector_registry._reset_for_testing(saved)


def _register() -> Collector:
    register_collector(
        key="unconfigured",
        cls=UnconfiguredCollector,
        scope="tap_plugin.administrivia.tests",
        name="Unconfigured test collector",
        description="Fixture collector for self-test UI.",
    )
    reconcile_collector_nodes()  # materialize the on-grid node (register is read-only)
    return Collector.objects.get(collector_registry="tap_plugin.administrivia.tests:unconfigured")


@pytest.mark.django_db
def test_table_self_test_button_queues_self_test_only_job(isolate_collector_registry):
    collector = _register()
    panel = Panel.objects.create(
        slug="cares-collector-table",
        name="CARES Collectors",
        view=CollectorTablePanelType.view,
    )
    request = RequestFactory().post(
        f"/panel/{panel.slug}--{panel.entity_id}/",
        {"action": "self_test", "collector_entity_id": str(collector.entity_id)},
    )

    response = CollectorTablePanelType.handle_post(panel, request)
    content = response.content.decode()

    assert response.status_code == 200
    # Queued flash, not an inline synchronous result. (The collector name is
    # HTML-escaped in the rendered flash, so assert on quote-free substrings.)
    assert "Self-test queued for" in content
    assert "Unconfigured test collector" in content
    assert "Open the collector page for full results" in content
    # The synchronous result block is gone from the table.
    assert "returned unconfigured" not in content
    # Table still renders with the action buttons.
    assert "Actions" in content
    assert "Self-test" in content
    assert "Run" in content

    # A self_test_only CollectionJob was created via run_collection.
    job = CollectionJob.objects.order_by("-enqueued_at").first()
    assert job is not None
    assert job.run_mode == CollectionJobRunMode.SELF_TEST_ONLY
    assert job.manual_run is True
    assert job.manual_run_source == "administrivia.collector_table.self_test"


@pytest.mark.django_db
def test_detail_self_test_button_queues_self_test_only_job(isolate_collector_registry):
    collector = _register()
    panel = Panel.objects.create(
        slug="cares-collector-detail",
        name="CARES Collector Detail",
        view=CollectorDetailPanelType.view,
    )
    request = RequestFactory().post(
        f"/panel/{panel.slug}--{panel.entity_id}/?entity_id={collector.entity_id}",
        {"action": "self_test", "collector_entity_id": str(collector.entity_id)},
    )

    response = CollectorDetailPanelType.handle_post(panel, request)
    content = response.content.decode()

    assert response.status_code == 200
    assert "Self-test queued for" in content
    assert "Unconfigured test collector" in content

    job = CollectionJob.objects.order_by("-enqueued_at").first()
    assert job is not None
    assert job.run_mode == CollectionJobRunMode.SELF_TEST_ONLY
    assert job.manual_run_source == "administrivia.collector_detail.self_test"


@pytest.mark.django_db(transaction=True)
def test_detail_renders_persisted_self_test_and_polls(isolate_collector_registry):
    """End-to-end: a self_test_only run persists self_test; the detail page
    renders that persisted readiness (no live self_test_collector call) and
    the self-test block carries the scoped HTMX poll."""
    collector = _register()

    # ImmediateBackend + transaction=True: phase-1 self-test runs, readiness is
    # unconfigured (non-runnable) so the job ends FAILED with self_test
    # persisted (req-tap-cares-collector-self-test-10).
    run_collection(collector, run_mode=CollectionJobRunMode.SELF_TEST_ONLY)

    panel = Panel.objects.create(
        slug="cares-collector-detail",
        name="CARES Collector Detail",
        view=CollectorDetailPanelType.view,
    )
    request = RequestFactory().get(f"/panel/{panel.slug}--{panel.entity_id}/?entity_id={collector.entity_id}")
    ctx = CollectorDetailPanelType.get_view_context(panel, request)

    readiness = ctx["collector"]["readiness"]
    assert readiness["known"] is True
    assert readiness["status"] == "unconfigured"
    assert readiness["runnable"] is False
    assert readiness["checked_at"]
    assert any(c["code"] == "CONFIG_PRESENT" for c in readiness["checks"])

    html = render_to_string(CollectorDetailPanelType.view, {"panel": panel, **ctx})
    # Self-test block is present, scoped-polls itself, hosts the relocated
    # Self-test button (action=self_test), and the Run button is its own form.
    assert 'id="cares-self-test-block"' in html
    assert 'hx-trigger="every 5s"' in html
    assert 'hx-select="#cares-self-test-block"' in html
    assert 'name="action" value="self_test"' in html
    assert 'name="action" value="run_collector"' in html
    assert "CONFIG_PRESENT" in html
