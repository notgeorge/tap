"""Forms and editor descriptors for LOTR Character entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms

from tap_web.editor import EditorDescriptor

if TYPE_CHECKING:
    from django.http import HttpRequest


class CharacterEditForm(forms.Form):
    """Edit form for Character fields.

    Covers the entity-level name plus Character-specific domain fields.
    """

    name = forms.CharField(
        max_length=255,
        strip=True,
        help_text="Character's canonical name.",
    )
    bio = forms.CharField(
        required=False,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Biography",
    )


class CharacterEditorDescriptor(EditorDescriptor):
    """Typed editor descriptor for LOTR Character objects."""

    entity_type = "character"
    form_class = CharacterEditForm
    editor_template = "lotr/character_editor.html"

    def get_editor_initial(self, obj: Any) -> dict[str, Any]:
        """Return initial values from entity name + character domain fields."""
        return {
            "name": obj.entity.name,
            "bio": obj.bio or "",
        }

    def handle_save(self, form: forms.Form, obj: Any, request: HttpRequest) -> Any:
        """Persist validated form data to the Character.

        BaseModel is the source of truth for `name` (via get_name()); the
        Entity.name spine value is a subordinate projection that obj.save()
        materializes. We therefore set the field on the node and never write
        Entity.name directly — a direct write is silently reverted by the
        spine sync (see spec-grid-node.md req-grid-node-display).
        """
        import uuid

        from django.contrib.auth import get_user_model

        from tap_grid.caller_context import CallerContext, set_caller_context

        cleaned = form.cleaned_data

        user = request.user if isinstance(request.user, get_user_model()) else None
        set_caller_context(CallerContext(user=user, batch_id=str(uuid.uuid7())))
        try:
            obj.name = cleaned["name"]
            obj.bio = cleaned.get("bio", "")
            obj.save(skip_validation=True)
        finally:
            set_caller_context(None)

        return obj
