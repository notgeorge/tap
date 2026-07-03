"""SARIF export shape tests (spec-tap-callsite-identity, guard-SARIF P4).

The live authz / direct-write baselines are empty on a green tree, so the exporter
emits zero *results* there — these tests drive the field mapping with synthetic
occurrences (a suppressed/baselined one and an active one) and confirm the envelope
on the real discovered guards.
"""

from __future__ import annotations

import json

import pytest

from tap.guards.base import REPO_ROOT
from tap.guards.callsite import CallsiteRatchet, RemediationUnit
from tap.guards.report import _FINGERPRINT_KEY, render_sarif
from tap.source_scan import CallSite, CallsiteIdentity


class _StubCallsiteRatchet(CallsiteRatchet):
    """A per-anchor callsite ratchet with injectable occurrences and baseline path."""

    map_row = "Stub surface"
    rid = "req-tap-auth-policy-9"  # a real, resolvable requirement
    description = "Stub callsite ratchet used only to exercise the SARIF field mapping."
    remediation_unit = RemediationUnit.PER_ANCHOR
    _occurrences: list[CallsiteIdentity] = []

    def collect(self) -> list[CallsiteIdentity]:
        return self._occurrences


# Set slug AFTER class creation so `__init_subclass__` does not register the stub
# into the global guard set (it is a test fixture, not a shipped guard).
_StubCallsiteRatchet.slug = "stub-callsite"


def _identity(qualname: str, sink: str, lineno: int, disc: str) -> CallsiteIdentity:
    path = REPO_ROOT / "tap_x" / "v.py"
    return CallsiteIdentity(
        location=CallSite(path, lineno),
        anchor=f"tap_x/v.py::{qualname}::{sink}",
        discriminator=disc,
    )


@pytest.fixture
def stub_guard(tmp_path):
    # Baselined (suppressed) occurrence in scope f; active (new) occurrence in scope g.
    suppressed = _identity("f", "write_batch", 12, "aaaa")
    active = _identity("g", "write_batch", 20, "bbbb")
    baseline = tmp_path / "stub_baseline.txt"
    # PER_ANCHOR baseline key == anchor; commit only the suppressed one's anchor.
    baseline.write_text(suppressed.anchor + "\n", encoding="utf-8")

    guard = _StubCallsiteRatchet()
    guard._occurrences = [suppressed, active]
    guard.baseline_path = baseline  # type: ignore[misc]  # instance override of ClassVar
    return guard, suppressed, active


def test_sarif_envelope(stub_guard):
    guard, _suppressed, _active = stub_guard
    doc = render_sarif([guard])

    assert doc["version"] == "2.1.0"
    assert "sarif-schema-2.1.0" in str(doc["$schema"])
    assert json.dumps(doc)  # fully serializable

    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "TAP Guards"
    rules = run["tool"]["driver"]["rules"]
    assert [r["id"] for r in rules] == ["stub-callsite"]
    assert rules[0]["properties"]["rid"] == "req-tap-auth-policy-9"
    assert rules[0]["properties"]["remediationUnit"] == "per-anchor"


def test_sarif_result_field_mapping(stub_guard):
    guard, suppressed, active = stub_guard
    results = render_sarif([guard])["runs"][0]["results"]
    assert len(results) == 2
    by_fp = {r["partialFingerprints"][_FINGERPRINT_KEY]: r for r in results}

    # occurrence_key IS the fingerprint — the discriminator keeps the two distinct.
    assert suppressed.occurrence_key in by_fp
    assert active.occurrence_key in by_fp
    assert suppressed.occurrence_key != active.occurrence_key

    r = by_fp[active.occurrence_key]
    assert r["ruleId"] == "stub-callsite"
    loc = r["locations"][0]
    assert loc["physicalLocation"]["artifactLocation"]["uri"] == "tap_x/v.py"  # repo-relative
    assert loc["physicalLocation"]["region"]["startLine"] == 20
    assert loc["logicalLocations"][0]["fullyQualifiedName"] == "g"  # qualname from anchor


def test_sarif_baselined_is_suppressed(stub_guard):
    guard, suppressed, active = stub_guard
    results = render_sarif([guard])["runs"][0]["results"]
    by_fp = {r["partialFingerprints"][_FINGERPRINT_KEY]: r for r in results}

    supp = by_fp[suppressed.occurrence_key]
    assert supp["suppressions"], "baselined debt must be emitted as a suppressed result"
    assert supp["suppressions"][0]["kind"] == "external"
    assert supp["properties"]["suppressed"] is True

    act = by_fp[active.occurrence_key]
    assert "suppressions" not in act, "a non-baselined finding is an active alert"
    assert act["properties"]["suppressed"] is False


def test_sarif_over_real_guards_is_wellformed():
    """The real discovered guards render a valid envelope; the two migrated callsite
    scanners appear as rules (results are empty on a green tree)."""
    doc = render_sarif()
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
    assert {"authz-coverage", "direct-write-coverage"} <= rule_ids
    assert isinstance(run["results"], list)
