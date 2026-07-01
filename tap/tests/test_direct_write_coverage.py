"""Direct-write scanner enforcement — req-tap-auth-policy-9 Rule B (write half).

Detect-by-default / permit-by-exception: a statically-resolvable class-level
direct write to a TAP-managed model (`<Model>.objects.create(...)`,
`<Model>.objects.filter(...).delete()`, `<Model>(...).save()`) outside the
sanctioned service layer is flagged, so node/edge mutations that bypass the
service layer are caught at authoring time. The runtime write backstop
(`tap_grid.write_guard`) catches the same class — including instance writes the
static tool cannot resolve — at execution time.

Baseline ratchet (mirrors the authz-coverage / log-site scanners): the flagged
set must equal `_direct_write_baseline.txt`. A NEW entry fails (route it through
the service layer, or annotate `# TAP-WRITE-COV: <reason>`, or last-resort
baseline it); a STALE entry fails (a fix must remove its line), so the baseline
ratchets to zero.
"""

from __future__ import annotations

from pathlib import Path

from tap.direct_write_coverage import scan_direct_writes
from tap.logging import CallSite, discover_scan_roots

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BASELINE_PATH = Path(__file__).resolve().parent / "_direct_write_baseline.txt"


def _tap_model_names() -> frozenset[str]:
    """Class names of every TAP-managed model — BaseModel subclasses (incl. Edge)
    plus the spine Entity. These are the graph models a direct write must not touch
    outside the service layer."""
    from django.apps import apps

    from tap_grid.models import BaseModel

    names = {m.__name__ for m in apps.get_models() if issubclass(m, BaseModel) and not m._meta.abstract}
    names.add("Entity")
    return frozenset(names)


def _key(site: CallSite) -> str:
    return f"{site.path.relative_to(_REPO_ROOT)}:{site.lineno}"


def _read_baseline() -> set[str]:
    if not _BASELINE_PATH.exists():
        return set()
    return {
        line.strip()
        for line in _BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_direct_write_ratchet() -> None:
    """Class-level direct writes to TAP models must equal the baseline."""
    result = scan_direct_writes(discover_scan_roots(_REPO_ROOT), _tap_model_names())
    baseline = _read_baseline()
    current = {_key(s) for s in result.direct_writes}

    new_entries = sorted(current - baseline)
    stale_entries = sorted(baseline - current)

    messages: list[str] = []
    if new_entries:
        listing = "\n  ".join(new_entries)
        messages.append(
            f"New direct writes to TAP-managed models not in baseline ({len(new_entries)}):\n  {listing}\n\n"
            "Node/edge mutations must route through the service layer (write_batch / create_node / "
            "create_edge / delete_* / patch_node), never direct ORM. Fix the call; if it is a "
            "sanctioned below-service write (admin/infra) annotate it `# TAP-WRITE-COV: <reason>`. "
            "Only as a last resort append the entries to tap/tests/_direct_write_baseline.txt."
        )
    if stale_entries:
        listing = "\n  ".join(stale_entries)
        messages.append(
            f"Baseline entries no longer match any violation ({len(stale_entries)}):\n  {listing}\n\n"
            "These were fixed or moved — remove the lines from "
            "tap/tests/_direct_write_baseline.txt. The baseline ratchets toward zero."
        )

    if messages:
        raise AssertionError("\n\n".join(messages))
