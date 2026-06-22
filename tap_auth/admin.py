"""tap_auth admin — registers the canonical User with actor-aware fieldsets.

This phase surfaces the new actor/built-in fields and makes the built-in
identity fields read-only in admin so they cannot be hand-edited into an
inconsistent state. Full protected-object mutation blocking (preventing
rename/delete/repurpose of protected built-ins and groups) is req-tap-auth-
builtins-4, landed with the built-in actors themselves in a later phase.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from tap_auth.models import User

_TAP_ACTOR_FIELDS = (
    "user_kind",
    "description",
    "description_json",
    "is_tap_builtin",
    "tap_builtin_key",
    "deactivated_at",
    "deactivated_reason",
    "deactivated_by_actor",
)


@admin.register(User)
class TapUserAdmin(UserAdmin):  # type: ignore[type-arg]
    """Django UserAdmin extended with TAP actor/built-in metadata."""

    # tap_builtin_key / is_tap_builtin are managed by bootstrap/sync code and are
    # immutable once set (req-tap-auth-builtins); never hand-edit them in admin.
    readonly_fields = ("is_tap_builtin", "tap_builtin_key")

    # Extend Django's defaults with the TAP actor metadata. Built from the base
    # class attrs via tuple-unpacking; the [misc] ignores cover django-stubs'
    # class-level access to these generically-typed instance attributes.
    fieldsets = (
        *UserAdmin.fieldsets,  # type: ignore[misc]
        (_("TAP actor"), {"fields": _TAP_ACTOR_FIELDS}),
    )
    list_display = (*UserAdmin.list_display, "user_kind", "is_tap_builtin")  # type: ignore[misc]
    list_filter = (*UserAdmin.list_filter, "user_kind", "is_tap_builtin")
