"""`CallsiteRatchet` — a ceiling ratchet whose findings carry full callsite identity.

This is the rich-record contract of `spec-tap-callsite-identity`
(`req-tap-callsite-identity-scan-rich-collapse-late`). A plain `CeilingRatchet`
forces every subclass to collapse its findings to a `set[str]` inside `measure()`,
*before* the harness sees them — so per-occurrence locations are lost and only the
baseline diff survives. That early collapse is exactly what blocks per-offense SARIF
export.

A `CallsiteRatchet` inverts it: the subclass implements ``collect()`` returning one
:class:`~tap.source_scan.CallsiteIdentity` **per physical offense** (location
preserved), and this base derives the baseline-key set *from* those records at
diff-prep time — the single legitimate collapse point. The un-collapsed
``collect()`` stream stays available to the SARIF export path, which never reduces
it (`req-tap-callsite-identity-scan-rich-collapse-late-2`).

The **remediation unit** picks which derived key becomes the baseline entry
(`req-tap-callsite-identity-remediation-unit`): a per-function scanner (one fix
clears every offense at an anchor — authz) keys on the *anchor*; a per-call scanner
(each offense fixed independently — direct-write) keys on the *occurrence_key*.

Additive by design: it extends `CeilingRatchet` without changing `measure()`'s
signature, so string-only ratchets (mypy's aggregate count) are untouched.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import replace
from typing import ClassVar

from tap.guards.base import CeilingRatchet
from tap.source_scan import CallsiteIdentity


class RemediationUnit(enum.Enum):
    """The granularity at which one fix clears a finding — sets the baseline key."""

    #: One fix (e.g. a function-level decorator) clears every offense at the anchor;
    #: the baseline keys on the anchor. Two offenses in one scope are one entry.
    PER_ANCHOR = "per-anchor"
    #: Each offense is remediated independently; the baseline keys on the
    #: occurrence_key, so byte-distinct offenses at one anchor are separate entries.
    PER_OCCURRENCE = "per-occurrence"


class CallsiteRatchet(CeilingRatchet):
    """A `CeilingRatchet` fed by per-occurrence `CallsiteIdentity` records."""

    #: How this scanner remediates — chooses anchor vs occurrence_key as baseline key.
    remediation_unit: ClassVar[RemediationUnit]

    @abc.abstractmethod
    def collect(self) -> list[CallsiteIdentity]:
        """One record per physical offense, each carrying its full location.

        This is the un-collapsed source of truth: the ratchet derives its
        baseline-key set from it, and the SARIF export consumes it directly.
        """

    def baseline_key(self, identity: CallsiteIdentity) -> str:
        """The ratchet entry for one occurrence, at this scanner's remediation unit."""
        if self.remediation_unit is RemediationUnit.PER_OCCURRENCE:
            return identity.occurrence_key
        return identity.anchor

    def measure(self) -> set[str]:
        """Collapse the rich records to the baseline-key set — the ONLY collapse point.

        `collect()` stays un-collapsed for the SARIF path; this reduction happens
        only here, at baseline-diff prep (`req-tap-callsite-identity-scan-rich-collapse-late-2`).
        """
        return {self.baseline_key(ci) for ci in self.collect()}


def disambiguate(identities: list[CallsiteIdentity]) -> list[CallsiteIdentity]:
    """Apply the ordinal fallback so every record keeps a distinct occurrence_key.

    The semantic-hash discriminator collides for byte-identical constructs at the
    same anchor (e.g. two identical ``entity.save()`` calls in one function). For a
    per-occurrence scanner those are genuinely separate offenses that must survive as
    separate entries, so when two records share an occurrence_key we append
    ``~<ordinal>`` (in scan order) to each — the fallback of
    `req-tap-callsite-identity-discriminator`. Records already unique are returned
    unchanged; reordering two *distinct* constructs does not swap their hashes, so
    only genuinely identical offenses are order-sensitive.
    """
    by_key: dict[str, list[int]] = {}
    for i, ci in enumerate(identities):
        by_key.setdefault(ci.occurrence_key, []).append(i)
    out = list(identities)
    for idxs in by_key.values():
        if len(idxs) == 1:
            continue
        for ordinal, i in enumerate(idxs, start=1):
            ci = identities[i]
            base = ci.discriminator
            out[i] = replace(ci, discriminator=f"{base}~{ordinal}" if base is not None else f"~{ordinal}")
    return out
