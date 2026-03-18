"""Text Panel — built-in panel type for plain text content.

Stores name and body text in the standard Panel object:
  - Panel.name           — display name
  - Panel.description    — backend/admin metadata (not rendered)
  - Panel.config["text"] — body text, rendered as plain text

Security: input sanitization via TextPanelEditForm (Django Form).
Rendering: Django auto-escaping ensures config.text is never treated as HTML.
"""

from django import forms


class TextPanelEditForm(forms.Form):
    """Edit form for Text Panel fields.

    All fields use strip=True (Django default) to sanitize whitespace.
    Server-side validation enforces max_length and required constraints
    independently of any browser-side checks (req-web-panel-edit-form.sec).
    """

    name = forms.CharField(max_length=255, strip=True)
    description = forms.CharField(required=False, strip=True, widget=forms.Textarea)
    text = forms.CharField(required=False, strip=True, widget=forms.Textarea, label="Body Text")


class TextPanelType:
    """Built-in text panel type descriptor.

    Attributes match the panel type contract used by panel_edit_view
    for form dispatch and by tap_web templates for rendering.
    """

    slug = "text"
    label = "Text Panel"
    view = "tap_web/panels/text_panel.html"
    editor_view = "tap_web/panels/text_panel_editor.html"
    config_defaults: dict = {"text": ""}
    form_class = TextPanelEditForm
