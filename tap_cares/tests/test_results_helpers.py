"""Tests for tap_cares.results.record_info / record_warn / record_error."""

from __future__ import annotations

import pytest
from jsonschema import ValidationError

from tap_cares.models import CollectionJob
from tap_cares.results import record_error, record_info, record_warn

# A pair of disposable UUIDv7 strings, used only inside this test module.
_FAKE_SITE_A = "019e1d29-7a3f-7c4d-8c00-0000000000a1"
_FAKE_SITE_B = "019e1d29-7a3f-7c4d-8c00-0000000000a2"
_FAKE_SITE_C = "019e1d29-7a3f-7c4d-8c00-0000000000a3"


def _make_job() -> CollectionJob:
    return CollectionJob.objects.create(name="test-job")


# ---------------------------------------------------------------------------
# Default shape
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDefaultResults:
    def test_default_is_three_empty_buckets(self):
        job = _make_job()
        assert job.results == {"info": [], "warn": [], "error": []}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRecordHappyPath:
    def test_record_info_appends_to_info_bucket(self):
        job = _make_job()
        record_info(job, _FAKE_SITE_A, "RUN_STARTED", "Run started.")
        job.refresh_from_db()
        assert len(job.results["info"]) == 1
        entry = job.results["info"][0]
        assert entry["site"] == _FAKE_SITE_A
        assert entry["code"] == "RUN_STARTED"
        assert entry["message"] == "Run started."
        assert entry["context"] == {}

    def test_record_warn_appends_to_warn_bucket(self):
        job = _make_job()
        record_warn(job, _FAKE_SITE_A, "FOO_WARN", "Mild concern.")
        job.refresh_from_db()
        assert len(job.results["warn"]) == 1
        assert job.results["info"] == []
        assert job.results["error"] == []

    def test_record_error_appends_to_error_bucket(self):
        job = _make_job()
        record_error(job, _FAKE_SITE_A, "MASS_DELETION", "Too many gone.")
        job.refresh_from_db()
        assert len(job.results["error"]) == 1

    def test_context_is_stored_verbatim(self):
        job = _make_job()
        record_info(
            job,
            _FAKE_SITE_A,
            "DIFF_COMPUTED",
            "Computed diff.",
            context={"new": 3, "modified": 1, "deprecated": 0},
        )
        job.refresh_from_db()
        assert job.results["info"][0]["context"] == {"new": 3, "modified": 1, "deprecated": 0}

    def test_multiple_appends_preserve_order(self):
        job = _make_job()
        record_info(job, _FAKE_SITE_A, "FIRST", "1st")
        record_info(job, _FAKE_SITE_B, "SECOND", "2nd")
        record_info(job, _FAKE_SITE_C, "THIRD", "3rd")
        job.refresh_from_db()
        codes = [e["code"] for e in job.results["info"]]
        assert codes == ["FIRST", "SECOND", "THIRD"]


# ---------------------------------------------------------------------------
# Schema rejection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSchemaRejection:
    def test_bad_site_format_rejected(self):
        job = _make_job()
        with pytest.raises(ValidationError):
            record_info(job, "not-a-uuid", "CODE", "msg")
        job.refresh_from_db()
        assert job.results["info"] == []

    def test_lowercase_code_rejected(self):
        job = _make_job()
        with pytest.raises(ValidationError):
            record_info(job, _FAKE_SITE_A, "lowercase", "msg")

    def test_code_with_hyphen_rejected(self):
        job = _make_job()
        with pytest.raises(ValidationError):
            record_info(job, _FAKE_SITE_A, "WITH-HYPHEN", "msg")

    def test_failed_validation_leaves_results_unchanged(self):
        job = _make_job()
        record_info(job, _FAKE_SITE_A, "GOOD", "ok")
        with pytest.raises(ValidationError):
            record_info(job, _FAKE_SITE_B, "bad-code", "fail")
        job.refresh_from_db()
        assert len(job.results["info"]) == 1
        assert job.results["info"][0]["code"] == "GOOD"

    def test_uuidv4_rejected(self):
        """The schema pins UUIDv7 specifically — version-4 UUIDs must fail."""
        job = _make_job()
        v4 = "12345678-1234-4234-9234-123456789abc"
        with pytest.raises(ValidationError):
            record_info(job, v4, "CODE", "msg")


# ---------------------------------------------------------------------------
# Required positional argument
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSiteIsRequiredPositional:
    def test_missing_site_raises_type_error(self):
        job = _make_job()
        with pytest.raises(TypeError):
            record_info(job, code="CODE", message="msg")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Persistence semantics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPersistence:
    def test_save_uses_update_fields_only(self):
        """A concurrent change to e.g. status (touched only by the task runtime)
        should not be clobbered by a record_* call. Simulate by mutating
        status on a fresh handle after a record_* call sees the original."""
        job_a = _make_job()
        job_b = CollectionJob.objects.get(pk=job_a.pk)

        # task-runtime-side: changes status, saves with its own update_fields
        from tap_cares.models import CollectionJobStatus

        job_b.status = CollectionJobStatus.RUNNING
        job_b.save(update_fields=["status"])

        # collector-side: appends a result via the helper (using its stale handle)
        record_info(job_a, _FAKE_SITE_A, "RUN_STARTED", "started")

        # Final DB state: status RUNNING preserved, results recorded.
        final = CollectionJob.objects.get(pk=job_a.pk)
        assert final.status == "RUNNING"
        assert len(final.results["info"]) == 1
