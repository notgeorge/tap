"""TAP development-time guards — findable, enumerable structural checks.

Guards are **distributed**: cross-cutting whole-repo guards live here in
`tap/guards/`; app- and plugin-owned guards live in their owner's `guards/` package
(`tap_cares/guards/`, `tap_grid/guards/`, `plugins/<slug>/…/guards/`). Each concrete
guard is one file; importing it registers its `Guard` subclass (see `base.py`).

`discover_guards()` (in `discovery.py`) walks every owner via the filesystem —
Django-registry-independent, so it runs pre-boot too — imports their guard modules,
and returns the full set. There is no runtime registry; discovery is the only step.

Adding a guard = drop a file in the right `guards/` package. No import list to edit.
"""

from __future__ import annotations

from tap.guards.base import (
    CeilingRatchet,
    Guard,
    all_guards,
    validation_map_surfaces,
)
from tap.guards.discovery import discover_guards

__all__ = [
    "Guard",
    "CeilingRatchet",
    "all_guards",
    "discover_guards",
    "validation_map_surfaces",
]
