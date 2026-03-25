"""TAP Web editor descriptor contract.

An EditorDescriptor defines how a typed TAP object plugs into the generic
editor shell defined in ``spec-web-editor.md``.

Registration (from an AppConfig.ready()):
    from tap_web.registry import register_editor
    register_editor(MyEditorDescriptor())

Discovery (from views):
    from tap_web.registry import get_editor
    descriptor = get_editor("character")  # None if not registered
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.forms import BaseForm
    from django.http import HttpRequest


class EditorDescriptor:
    """Base class for typed TAP object editors.

    Subclasses define how a specific entity type integrates with the generic
    editor shell.  Override ``entity_type``, ``form_class``, and the three
    required methods.

    Attributes:
        entity_type: Entity type slug handled by this descriptor (e.g. ``"character"``).
        form_class: Django Form or ModelForm class for the typed editor.
            May be ``None`` for descriptors that override ``get_form_class``.
        editor_template: Optional path to a custom form-field template.
            When absent the shell renders form fields generically.
    """

    entity_type: str = ""
    form_class: type | None = None
    editor_template: str = ""

    def get_form_class(self, obj: Any) -> type | None:
        """Return the form class for this object.

        Default implementation returns ``self.form_class``.  Override when
        form class must vary per instance (e.g. panel type dispatch).

        Args:
            obj: The typed model instance being edited.
        """
        return self.form_class

    def get_editor_template(self, obj: Any) -> str:
        """Return the editor form-field template path for this object.

        Default implementation returns ``self.editor_template``.  Override
        when the template varies per instance.

        Args:
            obj: The typed model instance being edited.
        """
        return self.editor_template

    def get_editor_initial(self, obj: Any) -> dict[str, Any]:
        """Return initial field values for the editor form.

        Args:
            obj: The typed model instance being edited.

        Returns:
            Dict of field name → initial value.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.get_editor_initial")

    def handle_save(self, form: BaseForm, obj: Any, request: HttpRequest) -> Any:
        """Persist validated form data to the object.

        Args:
            form: A valid (``is_valid() == True``) Django Form instance.
            obj: The typed model instance being edited.
            request: The current HTTP request.

        Returns:
            The (possibly updated) object instance.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.handle_save")

    def get_extra_context(self, obj: Any) -> dict[str, Any]:
        """Return extra template context merged into the editor context.

        Args:
            obj: The typed model instance being edited.
        """
        return {}
