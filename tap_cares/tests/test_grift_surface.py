"""Tests for tap_cares.grift.submit_collector_grift.

Covers req-tap-cares-collector-read-boundary (collector results route through
GRIFT) and req-tap-cares-collector-grift-import (GRIFT import surface).
"""

from __future__ import annotations

import uuid

import pytest

from tap_cares.collectors import CollectorBase
from tap_cares.grift import submit_collector_grift
from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.registry import collector_registry, register_collector
from tap_cares.services import enqueue_collection


@pytest.fixture
def isolate_collector_registry():
    saved = collector_registry.all()
    collector_registry._reset_for_testing()
    yield
    collector_registry._reset_for_testing(saved)


def _grift_doc(batch_id: str | None = None) -> dict:
    """Build a minimal valid GRIFT v0 document with one batch and one node."""
    batch_id = batch_id or str(uuid.uuid7())
    node_id = str(uuid.uuid7())
    return {
        "metadata": {"grift_version": "0"},
        "_reserved": {},
        "batches": [
            {
                "batch_entity": {
                    "entity_id": batch_id,
                    "entity_type": "batch",
                    "name": "tap_cares test batch",
                    "dimensions": {"tap_cares": "test"},
                },
                "batch_node": {
                    "source": "tap_cares.tests",
                    "name": "tap_cares test batch",
                    "description": "Minimal batch emitted by a test collector.",
                },
                "nodes": [
                    {
                        "entity": {
                            "entity_id": node_id,
                            "entity_type": "wanderer",
                            "name": "test-wanderer",
                            "dimensions": {"tap_cares": "test"},
                        },
                        "node": {
                            "name": "test-wanderer",
                            "journey": "",
                        },
                    }
                ],
                "edges": [],
            }
        ],
    }


def _make_collector(registry_key: str) -> Collector:
    return Collector.objects.create(
        name="Test Collector",
        description="",
        collector_registry=registry_key,
    )


# ---------------------------------------------------------------------------
# submit_collector_grift — direct helper usage
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitCollectorGrift:
    def test_returns_grift_import_result(self):
        job = CollectionJob.objects.create(name="job-1", status=CollectionJobStatus.RUNNING)
        result = submit_collector_grift(job, _grift_doc())
        assert result.success is True
        assert len(result.imported_batches) == 1

    def test_records_imported_batch_ids_on_job(self):
        job = CollectionJob.objects.create(name="job-2", status=CollectionJobStatus.RUNNING)
        doc = _grift_doc()
        expected_batch_id = doc["batches"][0]["batch_entity"]["entity_id"]
        submit_collector_grift(job, doc)
        job.refresh_from_db()
        assert expected_batch_id in job.grift_batches["imported"]

    def test_repeated_submission_appends(self):
        job = CollectionJob.objects.create(name="job-3", status=CollectionJobStatus.RUNNING)
        submit_collector_grift(job, _grift_doc())
        submit_collector_grift(job, _grift_doc())
        job.refresh_from_db()
        assert len(job.grift_batches["imported"]) == 2

    def test_skipped_batches_recorded(self):
        job = CollectionJob.objects.create(name="job-4", status=CollectionJobStatus.RUNNING)
        # First import succeeds; second import of the SAME batch entity_id should
        # be skipped per GRIFT's skip-if-already-imported guard.
        doc = _grift_doc()
        batch_id = doc["batches"][0]["batch_entity"]["entity_id"]
        submit_collector_grift(job, doc)
        submit_collector_grift(job, doc)
        job.refresh_from_db()
        # The same batch_id appears once in imported and once in skipped on re-submission.
        assert batch_id in job.grift_batches["imported"]
        assert batch_id in job.grift_batches["skipped"]


# ---------------------------------------------------------------------------
# End-to-end: collector run uses the helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEndToEndCollectorImport:
    def test_collector_can_submit_grift_during_run(self, isolate_collector_registry):
        captured_doc = _grift_doc()
        captured_doc_batch_id = captured_doc["batches"][0]["batch_entity"]["entity_id"]

        class ImportingCollector(CollectorBase):
            def run(self) -> None:
                from tap_cares.models import CollectionJob as Job

                job = Job.objects.get(entity_id=self.config.collection_job_entity_id)
                submit_collector_grift(job, captured_doc)

        register_collector("import-test", ImportingCollector, scope="tap_cares.tests.fakes")
        col = _make_collector("tap_cares.tests.fakes:import-test")
        job = enqueue_collection(col)
        job.refresh_from_db()
        assert job.status == CollectionJobStatus.SUCCESSFUL
        assert captured_doc_batch_id in job.grift_batches["imported"]
