"""Icon resolution service for TAP grid.

Owns the canonical icon lookup contract: given an EntityType, resolve the
static-relative path and full URL for its icon, or return None if no icon
is registered or the file does not exist on disk.

Validation fires at render time — missing icons are a safe fallback, not
an error (req-grid-icon-render-3). Registration does not require the file
to exist.

Convention
----------
Icons are stored as SVG files under each app/plugin's namespaced static
directory::

    {app}/static/{app_label}/icons/{icon_key}.svg

Static-relative path (for use with ``{% static %}`` or ``staticfiles_storage``)::

    {app_label}/icons/{icon_key}.svg
"""

import re

from django.apps import apps
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from tap_grid.models import EntityType

# Kebab-case: lowercase letters and digits, separated by hyphens.
# Must start with a letter.
_ICON_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def validate_icon_key(key: str) -> bool:
    """Return True if *key* is a valid kebab-case icon key."""
    return bool(_ICON_KEY_RE.match(key))


def resolve_icon_path(entity_type: EntityType) -> str | None:
    """Return the static-relative icon path for *entity_type*, or None.

    Returns None when:
    - The entity type has no icon key set.
    - The icon key fails kebab-case validation.
    - The owning app cannot be found in the app registry.
    - The resolved file does not exist in any staticfiles finder.

    Args:
        entity_type: The EntityType whose icon should be resolved.

    Returns:
        A static-relative path such as ``"lotr/icons/character.svg"``,
        suitable for passing to ``{% static %}``, or None.
    """
    key = entity_type.icon
    if not key:
        return None

    if not validate_icon_key(key):
        return None

    # Resolve the owning AppConfig by matching plugin_name to app config name.
    app_config = None
    for config in apps.get_app_configs():
        if config.name == entity_type.plugin_name:
            app_config = config
            break

    if app_config is None:
        return None

    static_path = f"{app_config.label}/icons/{key}.svg"

    # Render-time existence check — returns None gracefully if file is missing.
    if not finders.find(static_path):
        return None

    return static_path


def resolve_icon_url(entity_type: EntityType) -> str | None:
    """Return the full static URL for *entity_type*'s icon, or None.

    Suitable for use in serialized node data (e.g. Cytoscape ``icon_url``
    fields) or anywhere a full URL is required rather than a template tag.

    Args:
        entity_type: The EntityType whose icon URL should be resolved.

    Returns:
        A full URL string such as ``"/static/lotr/icons/character.svg"``,
        or None if no icon is available.
    """
    path = resolve_icon_path(entity_type)
    if path is None:
        return None
    return static(path)
