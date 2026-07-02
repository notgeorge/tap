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
        """Persist validated form data to the Character through the service layer.

        Routes the write through `patch_node` (never a direct `obj.save()`), so it
        carries grid.write + batch/FLIP/provenance and a caller lacking grid.write
        is denied (AuthzError → 403). BaseModel is the source of truth for `name`
        (via get_name()); the Entity.name spine value is a subordinate projection
        the write pipeline materializes — we set the node field and never write
        Entity.name directly (see spec-grid-node.md req-grid-node-display).
        """
        from tap_grid.services import patch_node

        cleaned = form.cleaned_data
        # Actor resolves from the ambient CallerContext (bound by the request
        # middleware / test fixture); patch_node authorizes it (grid.write).
        patch_node(
            target=obj.entity.pk,
            payload={"name": cleaned["name"], "bio": cleaned.get("bio", "")},
        )
        obj.refresh_from_db()
        return obj
