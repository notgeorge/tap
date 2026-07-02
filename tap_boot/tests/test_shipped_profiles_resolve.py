"""Every shipped boot profile resolves against the live registries.

The cheap, per-commit complement to the pre-push cold-boot gate's per-profile
smoke (spec-dev-validation.md `req-dev-validation-smoke-gate`): it discovers
every `boot/*.boot.json` and runs the zero-mutation resolve preflight
(`check_profile` → `_resolve_steps`) on each, asserting every enabled
`seed-plugin` slug/bundle and every `fire-collector` key resolves against the
in-memory registries.

This guard exists because of a concrete miss: the 2026-07-02 collector-identity
refactor (`register_collector` scope → plugin slug) repointed the grift
`SCHEDULED_TARGET` edges but left `boot/samsite.boot.json`'s four fire-collector
keys on their stale module-path scopes
(`tap_plugin.aws_core.collectors.boto3_collector.collector:boto3`), so
`manage.py boot --profile samsite` aborted at `_resolve_steps` — the live-demo
profile behind the active roadmap Done-Test, silently broken because `base` (the
default spawn, no collectors) stayed green. Schema-parse tests
(`test_profile.py`) could not catch it: a rotted key is well-formed JSON. This
resolves the *values* against the registry, which is the layer that rotted.

Registry-only (no DB): the resolve preflight mutates nothing.
"""

from __future__ import annotations

import pytest

from tap_boot.orchestrator import BootError, check_profile
from tap_boot.profile import BootProfile, FireCollectorStep, load_profile, profile_ids


def test_shipped_profiles_discovered():
    """The house profiles are present, so the parametrized guard is non-empty."""
    ids = set(profile_ids())
    assert {"base", "samsite"} <= ids, f"expected the base + samsite profiles; found {sorted(ids)}"


@pytest.mark.parametrize("profile_id", profile_ids())
def test_shipped_profile_resolves(profile_id: str):
    """Every enabled step in a shipped profile resolves against the registries.

    A stale/rotted fire-collector key or an unknown seed-plugin slug/bundle
    raises `BootError` here — offline, no grid mutation — exactly as the real
    boot would at its pre-resolution step, only sooner.
    """
    profile = load_profile(profile_id)
    try:
        check_profile(profile)
    except BootError as exc:  # pragma: no cover - the failure path is the point
        pytest.fail(
            f"shipped profile '{profile_id}' does not resolve against the registries: {exc}\n"
            f"A fire-collector key or seed-plugin slug/bundle has drifted from what is "
            f"actually registered (the module-path→slug rot class). Fix the profile in "
            f"boot/{profile_id}.boot.json."
        )


def test_guard_has_teeth_rotted_collector_key_fails():
    """The rot the guard exists to catch actually fails it (validate the validator).

    Reproduces the samsite break class: a well-formed profile whose
    fire-collector key uses the stale module-path scope instead of the
    registered `scope:key`. It parses fine but must not resolve.
    """
    rotted = BootProfile(
        profile_id="_teeth_check",
        version=1,
        description="synthetic rotted profile",
        on_failure="abort",
        steps=(
            FireCollectorStep(
                key="tap_plugin.fedramp_20x_ksi.collectors.ksi_catalog:ksi-catalog",
                enabled=True,
            ),
        ),
    )
    with pytest.raises(BootError):
        check_profile(rotted)
