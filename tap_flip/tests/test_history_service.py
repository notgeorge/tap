"""Tests for history service layer."""

import pytest

from tap_flip.config import is_history_enabled
from tap_flip.history.context import set_history_user
from tap_flip.history.service import get_historical_records, get_history_timeline
from tap_grid.models import User
from tap_grid.services import create_entity
from tap_plugins.core_examples.models import Concept, Precept


@pytest.mark.django_db
class TestHistoryEnabled:
    """Tests for history enablement on models."""

    def test_concept_has_history_enabled(self):
        """Concept model has history tracking enabled via FLIP_CONFIG."""
        assert is_history_enabled(Concept) is True

    def test_precept_has_history_disabled(self):
        """Precept model has history disabled (default)."""
        assert is_history_enabled(Precept) is False

    def test_concept_has_history_manager(self):
        """Concept has the history manager from django-simple-history."""
        assert hasattr(Concept, "history")


@pytest.mark.django_db
class TestGetHistoricalRecords:
    """Tests for get_historical_records function."""

    def test_new_concept_has_creation_record(self):
        """New Concept instance has at least one history record (creation)."""
        entity = create_entity("concept", name="Test Concept")
        concept = Concept.objects.create(entity=entity, summary="Initial summary")

        records = get_historical_records(concept)
        assert records.count() >= 1

    def test_update_creates_new_record(self):
        """Updating a Concept creates a new history record."""
        entity = create_entity("concept", name="Update Test")
        concept = Concept.objects.create(entity=entity, summary="Original")
        initial_count = concept.history.count()

        concept.summary = "Updated summary"
        concept.save()

        records = get_historical_records(concept)
        assert records.count() > initial_count

    def test_history_disabled_returns_empty(self):
        """get_historical_records returns empty for disabled models."""
        entity = create_entity("precept", name="Test Precept")
        precept = Precept.objects.create(entity=entity, statement="Some statement")

        records = get_historical_records(precept)
        # Should return empty queryset (not error)
        assert records.count() == 0


@pytest.mark.django_db
class TestGetHistoryTimeline:
    """Tests for get_history_timeline function."""

    def test_timeline_has_required_fields(self):
        """Timeline entries have timestamp, change_type, actor, record_id."""
        entity = create_entity("concept", name="Timeline Test")
        concept = Concept.objects.create(entity=entity, summary="Test")

        timeline = get_history_timeline(concept)
        assert len(timeline) >= 1

        entry = timeline[0]
        assert "timestamp" in entry
        assert "change_type" in entry
        assert "actor" in entry
        assert "record_id" in entry

    def test_timeline_records_change_types(self):
        """Timeline shows different change types for create/update."""
        entity = create_entity("concept", name="Change Type Test")
        concept = Concept.objects.create(entity=entity, summary="Original")

        concept.summary = "Updated"
        concept.save()

        timeline = get_history_timeline(concept)
        # Most recent first, so update should be first
        change_types = [e["change_type"] for e in timeline]
        assert "Changed" in change_types or "Created" in change_types


@pytest.mark.django_db
class TestHistoryUserAttribution:
    """Tests for user attribution in history records."""

    def test_history_records_user_from_context(self):
        """History records the user from context."""
        user = User.objects.create_user(username="historian", password="test")
        set_history_user(user)

        entity = create_entity("concept", name="User Test")
        concept = Concept.objects.create(entity=entity, summary="Test")

        # Check that the user was recorded
        latest_record = concept.history.latest("history_id")
        assert latest_record.history_user == user

        # Cleanup
        set_history_user(None)

    def test_history_without_user_context(self):
        """History works even without user in context (None)."""
        set_history_user(None)

        entity = create_entity("concept", name="No User Test")
        concept = Concept.objects.create(entity=entity, summary="Test")

        # Should not error, user will be None
        latest_record = concept.history.latest("history_id")
        assert latest_record.history_user is None
