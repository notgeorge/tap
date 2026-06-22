"""tap_auth models — TAP's canonical user / named-actor model.

`tap_auth.User` is TAP's `AUTH_USER_MODEL` (req-tap-auth-user-model). It is the
named-actor spine: every meaningful TAP operation resolves to a durable human or
program actor, and `User=None` is not valid at the service boundary
(req-tap-auth-actor-model). Protected built-in actors (the bootloader, the test
actor, future system/scheduler/collector actors) carry an immutable natural key
`tap_builtin_key` set only by tap_auth bootstrap/sync code (req-tap-auth-builtins).

This phase lands the model + fields only; capability/policy machinery, the
built-in actors themselves, and service-boundary enforcement arrive in later
phases. See tap_auth/specs/spec-tap-auth-v0.md.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class UserKind(models.TextChoices):
    """Actor kind vocabulary (req-tap-auth-actor-model).

    v1 supports two kinds; `program` covers every non-human actor (bootloader,
    test actor, service account, collector, scheduler, plugin runner, AI actor).
    """

    HUMAN = "human", "Human"
    PROGRAM = "program", "Program"


class User(AbstractUser):
    """TAP's canonical Django user and named actor.

    Extends Django `AbstractUser` with actor-kind, backend-managed context, and
    protected-built-in metadata. `is_active` (from AbstractUser) remains the
    login/enabled toggle; the `deactivated_*` fields record the auditable
    deactivation decision (reason, time, acting actor) layered on top.
    """

    user_kind = models.CharField(
        max_length=16,
        choices=UserKind.choices,
        default=UserKind.HUMAN,
        help_text="Actor kind: 'human' (a person) or 'program' (bootloader, collector, scheduler, AI, ...).",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Backend-managed operator/system context for this actor.",
    )
    description_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Backend-managed structured context, especially for program/AI actors.",
    )
    is_tap_builtin = models.BooleanField(
        default=False,
        help_text="True for TAP-managed protected built-in actors (req-tap-auth-builtins).",
    )
    tap_builtin_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        help_text=(
            "Immutable natural key for built-in actors (e.g. 'tap_bootloader'); "
            "null for ordinary users. Set only by tap_auth bootstrap/sync code."
        ),
    )
    deactivated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this actor was deactivated, if applicable.",
    )
    deactivated_reason = models.TextField(
        blank=True,
        default="",
        help_text="Why this actor was deactivated.",
    )
    deactivated_by_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deactivations_performed",
        help_text="The actor that performed the deactivation, where known.",
    )

    class Meta:
        db_table = "tap_user"
        constraints = [
            # A built-in actor must carry its immutable natural key
            # (req-tap-auth-builtins-3). Ordinary users leave it null.
            models.CheckConstraint(
                condition=models.Q(is_tap_builtin=False) | models.Q(tap_builtin_key__isnull=False),
                name="tap_auth_builtin_requires_key",
            ),
        ]

    def clean(self) -> None:
        """App-level mirror of the built-in-key constraint for form/admin paths."""
        super().clean()
        if self.is_tap_builtin and not self.tap_builtin_key:
            raise ValidationError({"tap_builtin_key": "Built-in actors require a tap_builtin_key."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforce `tap_builtin_key` immutability once set (req-tap-auth-builtins).

        The key is set-once: a row may go from null to a value (bootstrap minting
        a built-in), but an existing non-null key can never be changed or cleared
        by ordinary writes. DB uniqueness backs the per-key invariant; this guards
        the immutability the database cannot express directly.
        """
        if self.pk is not None:
            previous_key = type(self).objects.filter(pk=self.pk).values_list("tap_builtin_key", flat=True).first()
            if previous_key is not None and previous_key != self.tap_builtin_key:
                raise ValidationError({"tap_builtin_key": "tap_builtin_key is immutable once set."})
        super().save(*args, **kwargs)
