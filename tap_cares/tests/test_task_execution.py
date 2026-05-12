"""Tests for the Django Tasks-backed collector execution runtime.

Covers req-tap-cares-collector-task-execution and the lifecycle-update ACIDs
on the CollectionJob (req-tap-cares-collector-job-lifecycle-2, -3, -4) that
land with the runtime.

Uses Django's ImmediateBackend (configured in tap/settings.py), so enqueue()
runs the task synchronously and the CollectionJob has its terminal state by
the time enqueue_collection returns.
"""

from __future__ import annotations

import pytest

from tap_cares.collectors.config import CollectorConfig
from tap_cares.models import CollectionJobStatus, Collector
from tap_cares.registry import collector_registry, register_collector
from tap_cares.services import enqueue_collection
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


def _make_collector(registry_key: str, name: str = "Test Collector") -> Collector:
    return Collector.objects.create(
        name=name,
        description="",
        collector_registry=registry_key,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHappyPath:
    def test_run_succeeds_marks_job_successful(self, isolate_collector_registry):
        register_collector("happy", HappyCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:happy")
        job = enqueue_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.SUCCESSFUL
        assert job.started_at is not None
        assert job.finished_at is not None
        assert job.error_summary == ""

    def test_run_receives_correct_config(self, isolate_collector_registry):
        register_collector("happy", HappyCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:happy")
        job = enqueue_collection(col)
        assert HappyCollector.runs == [str(job.entity_id)]

    def test_has_job_edge_created(self, isolate_collector_registry):
        from tap_grid.models import Edge

        register_collector("happy", HappyCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:happy")
        job = enqueue_collection(col)

        edges = Edge.objects.filter(
            from_entity=col.entity,
            to_entity=job.entity,
            edge_type="HAS_JOB",
        )
        assert edges.count() == 1


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFailurePath:
    """The Django immediate backend captures task exceptions on the TaskResult
    instead of re-raising to the caller (see
    django/tasks/backends/immediate.py). `enqueue_collection` therefore returns
    normally even when the underlying collector raises; the failure surfaces
    via CollectionJob.status and error_summary."""

    def test_run_raises_marks_job_failed(self, isolate_collector_registry):
        register_collector("boom", BoomCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:boom")
        job = enqueue_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        assert "boom from BoomCollector" in job.error_summary
        assert job.finished_at is not None

    def test_unregistered_collector_marks_job_failed(self, isolate_collector_registry):
        col = _make_collector("tap_cares.tests.fakes:never-registered")
        job = enqueue_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        assert "CollectorNotFoundError" in job.error_summary

    def test_error_summary_capped_at_2048(self, isolate_collector_registry):
        from tap_cares.collectors import CollectorBase

        class LongBoom(CollectorBase):
            def run(self) -> None:
                raise RuntimeError("X" * 5000)

        register_collector("long", LongBoom, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:long")
        job = enqueue_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.FAILED
        assert len(job.error_summary) <= 2048


# ---------------------------------------------------------------------------
# task_result_id propagation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTaskResultIdPropagation:
    def test_task_result_id_populated(self, isolate_collector_registry):
        register_collector("happy", HappyCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:happy")
        job = enqueue_collection(col)
        assert job.task_result_id != ""
        assert len(job.task_result_id) <= 128


# ---------------------------------------------------------------------------
# Lifecycle timestamps
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLifecycleTimestamps:
    def test_enqueued_at_set_before_task(self, isolate_collector_registry):
        register_collector("happy", HappyCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:happy")
        job = enqueue_collection(col)
        assert job.enqueued_at is not None

    def test_started_at_before_finished_at(self, isolate_collector_registry):
        register_collector("happy", HappyCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:happy")
        job = enqueue_collection(col)
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
