"""Tests for the Django Tasks-backed collector execution runtime.

Covers req-tap-cares-collector-task-execution and the lifecycle-update ACIDs
on the CollectionJob (req-tap-cares-collector-job-lifecycle-2, -3, -4) that
land with the runtime.

Uses Django's ImmediateBackend (configured in tap/settings.py), so enqueue()
runs the task synchronously and the CollectionJob has its terminal state by
the time run_collection returns.
"""

from __future__ import annotations

import pytest

from tap_cares.collectors.config import CollectorConfig
from tap_cares.models import CollectionJobStatus, Collector
from tap_cares.registry import collector_registry, register_collector
from tap_cares.services import run_collection
from tap_cares.tests.fakes import BoomCollector, HappyCollector


@pytest.fixture
def isolate_collector_registry():
    saved = collector_registry.all()
    collector_registry._reset_for_testing()
    yield
    collector_registry._reset_for_testing(saved)


@pytest.fixture(autouse=True)
def reset_happy_runs():
    HappyCollector.runs.clear()
    yield
    HappyCollector.runs.clear()


def _register_and_fetch(key: str, cls, scope: str, *, name: str = "Test Collector") -> Collector:
    """Register a collector and fetch the resulting on-grid Collector node.

    Replaces the v0-pre-refactor pattern of `Collector.objects.create(...)` —
    `register_collector` now performs the on-grid upsert as part of the
    dual-existence registration. Tests fetch the resulting node by its
    canonical `collector_registry` value.
    """
    register_collector(
        key=key,
        cls=cls,
        scope=scope,
        name=name,
        description="Fixture collector for tap_cares.tests.test_task_execution.",
    )
    return Collector.objects.get(collector_registry=f"{scope}:{key}")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestHappyPath:
    def test_run_succeeds_marks_job_successful(self, isolate_collector_registry):
        col = _register_and_fetch("happy", HappyCollector, scope="tap_cares.tests.fakes")
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.SUCCESSFUL
        assert job.started_at is not None
        assert job.finished_at is not None
        # HappyCollector does not set self.summary, so the task body writes
        # an empty string on success.
        assert job.summary == ""

    def test_run_receives_correct_config(self, isolate_collector_registry):
        col = _register_and_fetch("happy", HappyCollector, scope="tap_cares.tests.fakes")
        job = run_collection(col)
        assert HappyCollector.runs == [str(job.entity_id)]

    def test_has_job_edge_created(self, isolate_collector_registry):
        from tap_grid.models import Edge

        col = _register_and_fetch("happy", HappyCollector, scope="tap_cares.tests.fakes")
        job = run_collection(col)

        edges = Edge.objects.filter(
            from_entity=col.entity,
            to_entity=job.entity,
            edge_type="HAS_JOB",
        )
        assert edges.count() == 1


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestFailurePath:
    """The Django immediate backend captures task exceptions on the TaskResult
    instead of re-raising to the caller (see
    django/tasks/backends/immediate.py). `run_collection` therefore returns
    normally even when the underlying collector raises; the failure surfaces
    via CollectionJob.status and summary."""

    def test_run_raises_marks_job_failed(self, isolate_collector_registry):
        col = _register_and_fetch("boom", BoomCollector, scope="tap_cares.tests.fakes")
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        # BoomCollector raises without calling record_error or setting
        # self.summary, so the task body falls back to the exception message.
        assert "boom from BoomCollector" in job.summary
        assert job.finished_at is not None

    def test_unregistered_collector_marks_job_failed(self, isolate_collector_registry):
        # Special case: this test simulates a Collector node whose runner is NOT
        # registered (the "uninstalled-plugin" scenario). We can't use
        # _register_and_fetch because it would register the runner too. Construct
        # the Collector node via the trusted-internal create path directly.
        from tap_grid.services import _create_node_internal_for_test

        result = _create_node_internal_for_test(
            "collector",
            {
                "name": "Never Registered",
                "description": "",
                "collector_registry": "tap_cares.tests.fakes:never-registered",
            },
        )
        assert result.success, result.errors
        col = Collector.objects.get(entity_id=result.entity_id)
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        assert "CollectorNotFoundError" in job.summary

    def test_summary_capped_at_2048(self, isolate_collector_registry):
        from tap_cares.collectors import CollectorBase

        class LongBoom(CollectorBase):
            def run(self) -> None:
                raise RuntimeError("X" * 5000)

        col = _register_and_fetch("long", LongBoom, scope="tap_cares.tests.fakes")
        job = run_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        assert len(job.summary) <= 2048


# ---------------------------------------------------------------------------
# task_result_id propagation
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestTaskResultIdPropagation:
    def test_task_result_id_populated(self, isolate_collector_registry):
        col = _register_and_fetch("happy", HappyCollector, scope="tap_cares.tests.fakes")
        job = run_collection(col)
        assert job.task_result_id != ""
        assert len(job.task_result_id) <= 128


# ---------------------------------------------------------------------------
# Lifecycle timestamps
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestLifecycleTimestamps:
    def test_enqueued_at_set_before_task(self, isolate_collector_registry):
        col = _register_and_fetch("happy", HappyCollector, scope="tap_cares.tests.fakes")
        job = run_collection(col)
        assert job.enqueued_at is not None

    def test_started_at_before_finished_at(self, isolate_collector_registry):
        col = _register_and_fetch("happy", HappyCollector, scope="tap_cares.tests.fakes")
        job = run_collection(col)
        job.refresh_from_db()
        assert job.started_at is not None and job.finished_at is not None
        assert job.started_at <= job.finished_at


# ---------------------------------------------------------------------------
# JSON-safe task args (req-tap-cares-collector-task-execution-3)
# ---------------------------------------------------------------------------


class TestTaskInputContract:
    def test_collector_config_is_two_uuids(self):
        from uuid import uuid4

        cfg = CollectorConfig(collector_entity_id=uuid4(), collection_job_entity_id=uuid4())
        # Must be reducible to JSON-safe data.
        import dataclasses

        as_dict = dataclasses.asdict(cfg)
        assert set(as_dict.keys()) == {"collector_entity_id", "collection_job_entity_id"}
