"""tap_auth models — TAP's canonical user / named-actor model.

`tap_auth.User` is TAP's `AUTH_USER_MODEL` (req-tap-auth-user-model). It is the
named-actor spine: every meaningful TAP operation resolves to a durable human or
program actor, and `User=None` is not valid at the service boundary
(req-tap-auth-actor-model). Protected built-in actors (the bootloader, scheduler,
collector, and the test actor) carry an immutable natural key `tap_builtin_key`
written by `tap_auth.sync` (req-tap-auth-builtins).

This module also holds the `Capability` table (the queryable DB projection of the
code capability registry) and `ProtectedGroup` metadata. The service-boundary
*enforcement* that consumes `authorize()` is wired in a later phase; see
tap_auth/specs/spec-tap-auth-v0.md.
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
            "null for ordinary users. Intended to be set only by tap_auth bootstrap/"
            "sync code; immutability is enforced at the application/save() layer."
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
            # Bidirectional: a built-in actor MUST carry its natural key, and an
            # ordinary user MUST NOT (req-tap-auth-builtins-3). The reverse half
            # is security-relevant — without it an ordinary user could reserve a
            # built-in key (e.g. 'tap_bootloader') and be silently adopted into a
            # privileged built-in by the next bootstrap get_or_create().
            models.CheckConstraint(
                condition=(
                    models.Q(is_tap_builtin=True, tap_builtin_key__isnull=False)
                    | models.Q(is_tap_builtin=False, tap_builtin_key__isnull=True)
                ),
                name="tap_auth_builtin_key_iff_builtin",
            ),
        ]

    def clean(self) -> None:
        """App-level mirror of the bidirectional built-in-key constraint."""
        super().clean()
        if self.is_tap_builtin and not self.tap_builtin_key:
            raise ValidationError({"tap_builtin_key": "Built-in actors require a tap_builtin_key."})
        if not self.is_tap_builtin and self.tap_builtin_key:
            raise ValidationError({"tap_builtin_key": "Only built-in actors may carry a tap_builtin_key."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforce `tap_builtin_key` immutability once set (req-tap-auth-builtins).

        The key is set-once: a row may go from null to a value (bootstrap minting
        a built-in), but an existing non-null key can never be changed or cleared.
        This is an **application-layer** invariant enforced here in save(); a raw
        ``QuerySet.update()`` or SQL bypasses it, as with any model-level invariant
        — `tap_auth.sync` is the sole intended writer of built-in keys. DB
        uniqueness backs the per-key invariant independently.
        """
        if self.pk is not None:
            previous_key = type(self).objects.filter(pk=self.pk).values_list("tap_builtin_key", flat=True).first()
            if previous_key is not None and previous_key != self.tap_builtin_key:
                raise ValidationError({"tap_builtin_key": "tap_builtin_key is immutable once set."})
        super().save(*args, **kwargs)


class Capability(models.Model):
    """A TAP capability — the queryable DB projection of the code registry.

    The canonical source of truth is `tap_auth.capabilities.CAPABILITIES`; this
    table is hard-synced from it (req-tap-auth-capabilities-3). It is a real table
    (not a managed=False placeholder) so capability descriptions + risk metadata
    are queryable from the DB/service layer — the affordance a future AI/Paladin
    actor needs (req-tap-auth-capabilities-7).

    Each Capability projects a backing Django `auth.Permission` (the Capability
    model is that permission's content-type home), so Groups still hold standard
    Django permissions while the capability metadata lives queryably here. TAP
    authorization resolves by the public `name`; the Permission is the storage
    Groups attach to.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Public TAP capability name, e.g. 'grid.read'.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Human-readable meaning of this capability.",
    )
    risk = models.CharField(
        max_length=16,
        default="medium",
        help_text="Risk/classification (low|medium|high|critical) from the registry.",
    )
    permission = models.OneToOneField(
        "auth.Permission",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tap_capability",
        help_text="The projected Django permission this capability is stored as.",
    )

    class Meta:
        db_table = "tap_capability"
        ordering = ["name"]
        verbose_name_plural = "capabilities"

    def __str__(self) -> str:
        return self.name


class ProtectedGroup(models.Model):
    """Metadata marking a Django `auth.Group` as a TAP-managed protected group.

    Django `Group` is not custom, so protected-group metadata lives here
    (req-tap-auth-builtins): a one-to-one to `auth.Group` plus an immutable
    natural `builtin_key` and an `is_protected` flag. Protected groups cannot be
    renamed/deleted/repurposed by ordinary user-management paths.
    """

    group = models.OneToOneField(
        "auth.Group",
        on_delete=models.CASCADE,
        related_name="tap_protected",
        help_text="The Django group this metadata protects.",
    )
    builtin_key = models.CharField(
        max_length=64,
        unique=True,
        help_text="Immutable natural key for the protected group, e.g. 'tap_admin'.",
    )
    is_protected = models.BooleanField(
        default=True,
        help_text="When true, the group is shielded from ordinary mutation/deletion.",
    )

    class Meta:
        db_table = "tap_protected_group"
        ordering = ["builtin_key"]

    def __str__(self) -> str:
        return self.builtin_key
