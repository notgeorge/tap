"""Template tags for TAP icon rendering.

Usage::

    {% load tap_icons %}
    {% entity_icon entity_type %}
    {% entity_icon entity_type css_class="w-6 h-6" %}

Icons are decorative (aria-hidden). Consumers that need object identity must
also render textual identity elsewhere (req-grid-icon-render-2).
"""

from django import template
from django.utils.html import format_html

from tap_grid.icon_service import resolve_icon_url
from tap_grid.models import EntityType

register = template.Library()


@register.simple_tag
def entity_icon(entity_type: EntityType, css_class: str = "") -> str:
    """Render an <img> tag for the entity type's icon, or empty string.

    Args:
        entity_type: The EntityType whose icon should be rendered.
        css_class: Optional CSS class string applied to the <img> element.

    Returns:
        A safe HTML ``<img>`` tag, or an empty string if no icon is available.
    """
    url = resolve_icon_url(entity_type)
    if not url:
        return ""
    return format_html(
        '<img src="{}" class="{}" alt="" aria-hidden="true">',
        url,
        css_class,
    )
