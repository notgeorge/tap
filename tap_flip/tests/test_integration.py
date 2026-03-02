"""Integration tests for FLIP Phase 1 (history tracking).

Tests the full flow: context → model save → history recording.
"""

import pytest

from tap_grid.models import User
from tap_grid.services import create_entity
from tap_flip.config import is_history_enabled
from tap_flip.history import get_historical_records, get_history_timeline, set_history_user
from tap_plugins.core_examples.models import Concept, Precept


@pytest.mark.django_db
class TestFullHistoryFlow:
    """End-to-end tests for history tracking flow."""

    def test_create_update_history_flow(self):
        """Full flow: create → update → query history."""
        # Set user context
        user = User.objects.create_user(username="flowtest", password="test")
        set_history_user(user)

        # Create a concept
        entity = create_entity("concept", display_name="Flow Test Concept")
        concept = Concept.objects.create(entity=entity, summary="Original summary")

        # Update it
        concept.summary = "Updated summary"
        concept.save()

        # Query history
        records = get_historical_records(concept)
        timeline = get_history_timeline(concept)

        # Verify
        assert records.count() == 2  # Create + Update
        assert len(timeline) == 2
        assert timeline[0]["actor"] == "flowtest"

        # Cleanup
        set_history_user(None)

    def test_history_preserves_old_values(self):
        """History records preserve the state at each point in time."""
        entity = create_entity("concept", display_name="Preserve Test")
        concept = Concept.objects.create(entity=entity, summary="Version 1")

        concept.summary = "Version 2"
        concept.save()

        concept.summary = "Version 3"
        concept.save()

        # Get all historical records
        records = list(concept.history.all().order_by("history_date"))

        # Should have 3 records with different summaries
        assert len(records) == 3
        assert records[0].summary == "Version 1"
        assert records[1].summary == "Version 2"
        assert records[2].summary == "Version 3"


@pytest.mark.django_db
class TestBatchIdFieldExists:
    """Tests for batch_id field on BaseModel."""

    def test_batch_id_field_exists_on_concept(self):
        """Concept model has batch_id field."""
        entity = create_entity("concept", display_name="Batch ID Test")
        concept = Concept.objects.create(entity=entity, summary="Test")

        # batch_id should exist and be empty string in Phase 1
        assert hasattr(concept, "batch_id")
        assert concept.batch_id == ""

    def test_batch_id_can_be_set(self):
        """batch_id field can be set (for Phase 2 preparation)."""
        entity = create_entity("concept", display_name="Batch Set Test")
        concept = Concept.objects.create(entity=entity, summary="Test")

        batch_uuid = "019468b7-1234-7def-8000-000000000001"
        concept.batch_id = batch_uuid
        concept.save()

        concept.refresh_from_db()
        assert concept.batch_id == batch_uuid

    def test_batch_id_field_exists_on_precept(self):
        """Precept model also has batch_id field (inherited from BaseModel)."""
        entity = create_entity("precept", display_name="Precept Batch Test")
        precept = Precept.objects.create(entity=entity, statement="Test statement")

        assert hasattr(precept, "batch_id")
        assert precept.batch_id == ""


@pytest.mark.django_db
class TestHistoryEnabledVsDisabled:
    """Tests contrasting history-enabled vs disabled models."""

    def test_concept_enabled_precept_disabled(self):
        """Concept has history, Precept does not."""
        assert is_history_enabled(Concept) is True
        assert is_history_enabled(Precept) is False

    def test_concept_has_history_manager(self):
        """Concept has the history manager."""
        assert hasattr(Concept, "history")

    def test_precept_no_history_manager(self):
        """Precept does not have history manager (or it returns empty)."""
        # Precept may or may not have the manager depending on implementation
        # but get_historical_records should return empty
        entity = create_entity("precept", display_name="No History Test")
        precept = Precept.objects.create(entity=entity, statement="Test")

        records = get_historical_records(precept)
        assert records.count() == 0

    def test_both_have_batch_id(self):
        """Both Concept and Precept have batch_id (BaseModel field)."""
        concept_entity = create_entity("concept", display_name="C")
        precept_entity = create_entity("precept", display_name="P")

        concept = Concept.objects.create(entity=concept_entity, summary="Test")
        precept = Precept.objects.create(entity=precept_entity, statement="Test")

        assert hasattr(concept, "batch_id")
        assert hasattr(precept, "batch_id")
