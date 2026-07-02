"""Direct-write coverage ratchet — `req-tap-auth-policy-9` Rule B (write half).

A statically-resolvable class-level direct write to a TAP-managed model
(`<Model>.objects.create(...)`, `<Model>.objects.filter(...).delete()`,
`<Model>(...).save()`) outside the sanctioned service layer bypasses provenance,
authorization, and history. The scanner flags them at authoring time; the runtime
write backstop (`tap_grid.write_guard`) catches the same class — including instance
writes the static tool cannot resolve — at execution time.

Migrated onto the shared ratchet harness (`tap.ratchet` via `CeilingRatchet`): the
flagged set must equal `_direct_write_baseline.txt`, which ratchets toward zero.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tap.guards.base import REPO_ROOT, CeilingRatchet


class DirectWriteRatchet(CeilingRatchet):
    slug = "direct-write-coverage"
    map_row = "Direct-write coverage"
    description = (
        "A direct ORM write to a TAP-managed model outside the service layer bypasses provenance, "
        "authorization, and history — the graph mutates with no record of who/why. This flags the "
        "statically-resolvable cases at authoring time; the runtime write_guard catches the rest. "
        "It is the write half of the authz-coverage story and ratchets toward zero."
    )
    baseline_path: ClassVar[Path] = REPO_ROOT / "tap" / "tests" / "_direct_write_baseline.txt"
    new_hint = (
        "Node/edge mutations must route through the service layer (write_batch / create_node / "
        "create_edge / delete_* / patch_node), never direct ORM. Fix the call; if it is a "
        "sanctioned below-service write (admin/infra) annotate it `# TAP-WRITE-COV: <reason>`."
    )

    def measure(self) -> set[str]:
        from tap.direct_write_coverage import scan_direct_writes
        from tap.source_scan import first_party_source_roots

        result = scan_direct_writes(first_party_source_roots(REPO_ROOT), _tap_model_names())
        return {f"{s.path.relative_to(REPO_ROOT)}:{s.lineno}" for s in result.direct_writes}


def _tap_model_names() -> frozenset[str]:
    """Class names of every TAP-managed model — BaseModel subclasses (incl. Edge) plus Entity."""
    from django.apps import apps

    from tap_grid.models import BaseModel

    names = {m.__name__ for m in apps.get_models() if issubclass(m, BaseModel) and not m._meta.abstract}
    names.add("Entity")
    return frozenset(names)
