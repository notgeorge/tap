"""Tests for history context management (contextvars)."""

import pytest

from tap_flip.history.context import (
    get_batch_id,
    get_history_user,
    set_batch_id,
    set_history_user,
)
from tap_grid.models import User


class TestHistoryUserContext:
    """Tests for history user context management."""

    def test_default_user_is_none(self):
        """Unset context returns None."""
        # Reset to default state
        set_history_user(None)
        assert get_history_user() is None

    @pytest.mark.django_db
    def test_set_and_get_user(self):
        """Can set and retrieve user from context."""
        user = User.objects.create_user(username="testuser", password="testpass")
        set_history_user(user)
        assert get_history_user() == user
        # Cleanup
        set_history_user(None)

    def test_set_user_to_none_clears_context(self):
        """Can clear user context by setting to None."""
        set_history_user(None)
        assert get_history_user() is None


class TestBatchIdContext:
    """Tests for batch_id context management."""

    def test_default_batch_id_is_none(self):
        """Unset context returns None."""
        set_batch_id(None)
        assert get_batch_id() is None

    def test_set_and_get_batch_id(self):
        """Can set and retrieve batch_id from context."""
        batch_id = "019468b7-1234-7def-8000-000000000001"
        set_batch_id(batch_id)
        assert get_batch_id() == batch_id
        # Cleanup
        set_batch_id(None)

    def test_clear_batch_id(self):
        """Can clear batch_id context."""
        set_batch_id("some-batch-id")
        set_batch_id(None)
        assert get_batch_id() is None


class TestContextIsolation:
    """Tests for context isolation between operations."""

    @pytest.mark.django_db
    def test_user_and_batch_are_independent(self):
        """User and batch_id contexts are independent."""
        user = User.objects.create_user(username="isolation", password="test")

        set_history_user(user)
        set_batch_id("batch-123")

        assert get_history_user() == user
        assert get_batch_id() == "batch-123"

        # Clear one doesn't affect the other
        set_history_user(None)
        assert get_history_user() is None
        assert get_batch_id() == "batch-123"

        # Cleanup
        set_batch_id(None)
