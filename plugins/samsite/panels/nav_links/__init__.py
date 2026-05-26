"""Samsite Nav Links — small static-link-card panel type.

Renders a list of `{label, href, description}` link cards from
`panel.config.links`. Used to provide one-click discovery from existing
Samsite pages to sibling pages (e.g. the OSCAL workbench pages contributed
by `spec-samsite-compliance-pages-v0.md`).

No `get_view_context` override — the template reads directly from
`panel.config`, with Django auto-escaping protecting every field.

Spec: plugins/samsite/specs/spec-samsite-compliance-pages-v0.md
      (req-samsite-pages-discovery)
"""

from typing import Any, ClassVar


class NavLinksPanelType:
    slug: ClassVar[str] = "samsite-nav-links"
    label: ClassVar[str] = "Samsite Nav Links"
    view: ClassVar[str] = "samsite/panels/nav_links.html"
    css: ClassVar[list[str]] = ["samsite/css/panel-nav-links.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {"links": []}
