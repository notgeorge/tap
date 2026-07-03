"""Shared source-scanning primitives for TAP's static, tree-walking checks.

Several checks walk the first-party source tree and report findings by file+line:
the log-site token scanner (`tap.logging`), the authz-coverage scanner
(`tap.authz_coverage`), the direct-write scanner, the plugin-dependency scanner
(`tap.plugin_deps`), and — soon — guard discovery. They all need the same two
things: *which roots count as first-party TAP source*, and *a way to name a source
location*. Those primitives lived in `tap.logging` because the log-site scanner was
the first caller; they are not logging-specific and now live here.

Deliberately Django-free: `first_party_source_roots` inspects the filesystem, not
Django's app registry, so a caller can run **before** `django.setup()` — at pytest
collection time, inside a pre-boot gate, or from a bare script.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CallSite:
    """A source-code location: a file path and a 1-indexed line number.

    The shared currency of the tree-scanners — a finding is "this thing, here".
    Scanners layer their own richer result types on top (e.g. the log-site
    scanner's `WellFormedSite` adds the hex token).

    In the callsite-identity model (`spec-tap-callsite-identity`) this is the
    **location** role — the navigable, freely-drifting part of a finding. It is
    never part of the drift-proof anchor or either derived key.
    """

    path: Path
    lineno: int


@dataclass(frozen=True)
class CallsiteIdentity:
    """A tree-scanner finding's three-role identity (`spec-tap-callsite-identity`).

    Separates the drift-proof structural **anchor** (`path::qualname::construct`,
    never a line number) from the physical **location** (navigation only, drifts)
    and an optional occurrence **discriminator** (present only when an anchor can
    cover more than one physical offense). Two keys compose from these:

    - ``occurrence_key`` — ``anchor`` (+ ``#<discriminator>``): exactly one physical
      offense; the SARIF fingerprint. Computed here.
    - the *baseline key* — the ratchet's entry identity, at remediation-unit
      granularity (anchor for per-function scanners, occurrence_key for per-call
      ones). NOT computed here: it is the ratchet's choice, so it lives on
      ``CallsiteRatchet`` (`req-tap-callsite-identity-remediation-unit`), not on the
      identity.

    The anchor is the single drift-proof *root* both keys derive from; it is not
    itself either key.
    """

    location: CallSite
    anchor: str
    discriminator: str | None = None

    @property
    def occurrence_key(self) -> str:
        """The anchor, plus ``#<discriminator>`` when one is present — one per offense."""
        if self.discriminator is None:
            return self.anchor
        return f"{self.anchor}#{self.discriminator}"


def semantic_hash(*parts: str) -> str:
    """A short, stable digest over **location-free** canonical material.

    The shared discriminator recipe (`req-tap-callsite-identity-discriminator`), so
    the tree-scanners do not each invent their own hash. Callers pass their
    scanner-owned canonical parts — the repo-relative POSIX path, the enclosing
    qualname, the construct kind, `Model.op`, and a positions-stripped
    ``ast.dump(node, include_attributes=False)`` — and **never** a raw line or
    column, which is what keeps the digest drift-proof. Byte-identical constructs
    collide by design; the caller applies an ordinal fallback (see
    `tap.guards.callsite.disambiguate`).
    """
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


def first_party_source_roots(project_root: Path) -> list[Path]:
    """The first-party TAP source roots every tree-scanner walks.

    Returns the `tap_*` app roots (a directory with `apps.py`) plus the in-repo
    plugin roots (a `tap-plugin.toml`-bearing directory under `plugins/<slug>`),
    discovered by **filesystem inspection**.

    Two in-repo plugin layouts are recognized so package-mode migration does not
    silently drop a plugin from a scanner:
      - build-baked / legacy:  `plugins/<slug>/tap-plugin.toml`               → root `plugins/<slug>`
      - package-mode namespace: `plugins/<slug>/tap_plugin/<slug>/tap-plugin.toml` → root that package dir
    (A fully extracted package-mode plugin installed from site-packages is out of the
    in-repo scanners' scope by construction; its scanning moves with its own repo.)

    Independent of Django's runtime app registry — a hard guarantee, not an
    incidental one: callers run this at pytest collection time and inside the
    pre-boot gate, before settings/apps are loaded.
    """
    roots: list[Path] = []
    for child in sorted(project_root.iterdir()):
        if child.is_dir() and child.name.startswith("tap_") and (child / "apps.py").exists():
            roots.append(child)
    plugins_dir = project_root / "plugins"
    if plugins_dir.is_dir():
        for child in sorted(plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            if (child / "tap-plugin.toml").exists():
                roots.append(child)  # legacy flat layout
                continue
            # Package-mode: manifest sits inside the PEP 420 namespace at
            # plugins/<slug>/tap_plugin/<pkg>/tap-plugin.toml (req-plugin-arch-identity-3).
            namespace_dir = child / "tap_plugin"
            if namespace_dir.is_dir():
                roots.extend(sorted(m.parent for m in namespace_dir.glob("*/tap-plugin.toml")))
    return roots
