"""tap_web utilities — shared rendering helpers."""

import json
from typing import Any


def safe_json(value: Any) -> str:
    """Serialize *value* to a JSON string safe for embedding in HTML ``<script>`` blocks.

    After ``json.dumps``, the three HTML-significant characters ``<``, ``>``,
    and ``&`` are replaced with their Unicode escape equivalents so the output
    can be used with ``{{ json_str|safe }}`` inside a ``<script>`` tag without
    risking premature tag termination or entity injection.

    This mirrors the escaping performed by Django's ``json_script`` template
    filter.  See ``req-web-panel-json-embed.sec`` in
    ``tap_web/specs/spec-web-panel-security.md``.
    """
    raw = json.dumps(value)
    return raw.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
