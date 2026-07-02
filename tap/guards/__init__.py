"""TAP development-time guards — findable, enumerable structural checks.

Importing this package imports every guard module below, so each concrete `Guard`
registers (via subclass enumeration) and `all_guards()` sees the full set. This is
the only "discovery" step; there is no runtime registry (see `base.py`).

Migrating a ratchet/guard onto the harness = add a module here + import it below.
"""

from __future__ import annotations

# --- guard modules (import so their subclasses register) --------------------
from tap.guards import (  # noqa: F401  (imported for registration side effect)
    authz,
    cares,
    collection,
    direct_write,
    gryphon_coverage,
    json_files,
    log_sites,
    mypy_ratchet,
    secrets,
    service_gateway,
)
from tap.guards.base import (
    CeilingRatchet,
    Guard,
    all_guards,
    validation_map_surfaces,
)

__all__ = [
    "Guard",
    "CeilingRatchet",
    "all_guards",
    "validation_map_surfaces",
]
