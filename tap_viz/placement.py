"""The graph placement algorithm used when a layout does not name one.

A leaf module with no imports: both the graph panel (tap_viz) and the web views that
render graph context (tap_web) read this default, and ``tap_viz.panels.graph_panel``
imports ``tap_web`` at module scope — so a home inside the panel package would force
``tap_web`` into a cycle and back into function-local imports.
"""

from typing import Final

DEFAULT_PLACEMENT: Final[str] = "cytoscape:cose"
