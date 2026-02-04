"""
TAP Core Models
=============================================================================
Core data models for the TAP platform. This is the foundation everything
else builds on.

Key models:
    User        - Custom user model (extends Django's AbstractUser)
    Entity      - The atomic unit of meaning in TAP (authoritative system of record)
    Edge        - Directed, typed relationship between two entities

Design philosophy: See DESIGN.md in this directory.
"""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model for TAP.

    Extends Django's AbstractUser to allow adding fields later without
    the pain of changing AUTH_USER_MODEL after migrations exist.

    For now this is intentionally minimal - it inherits everything from
    AbstractUser (username, email, password, first_name, last_name, etc.)
    """

    class Meta:
        db_table = "tap_user"
