"""Direct-write coverage ratchet — `req-tap-auth-policy-9` Rule B (write half).

A statically-resolvable class-level direct write to a TAP-managed model
(`<Model>.objects.create(...)`, `<Model>.objects.filter(...).delete()`,
`<Model>(...).save()`) outside the sanctioned service layer bypasses provenance,
authorization, and history. The scanner flags them at authoring time; the runtime
write backstop (`tap_grid.write_guard`) catches the same class — including instance
writes the static tool cannot resolve — at execution time.

Migrated onto the shared ratchet harness (`tap.ratchet` via `CallsiteRatchet`): the
flagged set must equal `baselines/direct_write.txt`, which ratchets toward zero.
Remediation is **per-call** (each write is individually rerouted), so the baseline
keys on the drift-proof occurrence_key `path::qualname::Model.op#<disc>`, not the
line number — see `spec-tap-callsite-identity` (`req-tap-callsite-identity-remediation-unit`).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from tap.guards.base import REPO_ROOT, Guard
from tap.guards.callsite import CallsiteRatchet, RemediationUnit, disambiguate
from tap.source_scan import CallSite, CallsiteIdentity

if TYPE_CHECKING:
    from tap.direct_write_coverage import ManagedModelIndex


class DirectWriteRatchet(CallsiteRatchet):
    slug = "direct-write-coverage"
    map_row = "Direct-write coverage"
    rid = "req-tap-auth-policy-9"
    description = (
        "A direct ORM write to a TAP-managed model outside the service layer bypasses provenance, "
        "authorization, and history — the graph mutates with no record of who/why. This flags the "
        "statically-resolvable cases at authoring time; the runtime write_guard catches the rest. "
        "It is the write half of the authz-coverage story and ratchets toward zero."
    )
    baseline_path: ClassVar[Path] = Path(__file__).resolve().parent / "baselines" / "direct_write.txt"
    #: Per-call: each write is rerouted independently, so the baseline keys on the
    #: occurrence_key (two identical writes in one function are two entries).
    remediation_unit: ClassVar[RemediationUnit] = RemediationUnit.PER_OCCURRENCE
    new_hint = (
        "Node/edge mutations must route through the service layer (write_batch / create_node / "
        "create_edge / delete_* / patch_node), never direct ORM. Fix the call; if it is a "
        "sanctioned below-service write (admin/infra) annotate it `# TAP-WRITE-COV: <reason>`."
    )

    def collect(self) -> list[CallsiteIdentity]:
        from tap.direct_write_coverage import scan_direct_writes
        from tap.source_scan import first_party_source_roots

        result = scan_direct_writes(first_party_source_roots(REPO_ROOT), _managed_model_index())
        identities = [
            CallsiteIdentity(
                location=CallSite(s.path, s.lineno),
                anchor=s.anchor(REPO_ROOT),
                discriminator=s.discriminator(REPO_ROOT),
            )
            for s in result.direct_writes
        ]
        return disambiguate(identities)


class DirectWriteExemptionGuard(Guard):
    """Fail a `# TAP-WRITE-COV` exemption that no longer suppresses any flagged write.

    An exemption is a reviewed promise that *this specific* direct write is a sanctioned
    below-service exception. When the write it covered is rerouted onto the service
    layer, resolved out of the scanner's scope, or simply moved off the comment's span,
    the promise is stale: it silences nothing today, and it lies in wait to silence a
    *different* future write that lands on its line — the true-but-orthogonal-reason
    failure mode. This makes stale exemptions rot loudly, the way mypy's
    `warn_unused_ignores` and Pylint's `useless-suppression` do.
    """

    slug = "direct-write-unused-exemption"
    map_row = "Direct-write exemption freshness"
    rid = "req-tap-auth-policy-9-unused-exemption"
    description = (
        "A `# TAP-WRITE-COV` exemption on a line the direct-write scanner no longer flags is a stale "
        "excuse — the write it justified is gone or now out of scope, so the comment silences nothing "
        "and could later mask an unrelated write on its line. Fails such orphaned exemptions so they "
        "rot loudly (mypy `warn_unused_ignores` / Pylint `useless-suppression`)."
    )

    def check(self) -> None:
        from tap.direct_write_coverage import scan_direct_writes
        from tap.source_scan import first_party_source_roots

        result = scan_direct_writes(first_party_source_roots(REPO_ROOT), _managed_model_index())
        if result.unused_exemptions:
            locs = ", ".join(f"{c.path.relative_to(REPO_ROOT)}:{c.lineno}" for c in result.unused_exemptions)
            raise AssertionError(
                f"{len(result.unused_exemptions)} stale `# TAP-WRITE-COV` exemption(s) suppress no flagged "
                f"direct write — remove each (the write it covered is gone or now out of scope): {locs}."
            )


def _managed_model_index() -> ManagedModelIndex:
    """Index of every TAP-managed model class — BaseModel subclasses (incl. Edge) plus
    Entity — with the collision-resolution data (app roots per name) the scanner needs to
    tell a same-named non-managed class apart (`req-tap-auth-policy-9-name-resolution`)."""
    from django.apps import apps

    from tap.direct_write_coverage import CollisionResolution, ManagedModelIndex
    from tap_grid.models import BaseModel

    managed: dict[str, set[str]] = {}
    nonmanaged: dict[str, set[str]] = {}
    for model in apps.get_models():
        if model._meta.abstract:
            continue
        bucket = managed if issubclass(model, BaseModel) else nonmanaged
        bucket.setdefault(model.__name__, set()).add(model._meta.app_config.name)

    names = set(managed)
    names.add("Entity")  # the spine node — not a BaseModel, always graph-managed.
    collisions = {
        name: CollisionResolution(frozenset(managed[name]), frozenset(nonmanaged[name]))
        for name in managed
        if name in nonmanaged
    }
    return ManagedModelIndex(frozenset(names), collisions)
