"""run_boot orchestration: auth → population, pre-resolution, on_failure (req-boot-phases/population).

These are fresh-test-DB integration tests — pytest-django builds the DB and the
session `sync_auth` baseline runs first; each `run_boot` then converges it again.
"""

from __future__ import annotations

import logging

import pytest
from django.core.management.base import BaseCommand

from tap.plugin_testing import requires_plugins
from tap_auth.actors import BOOTLOADER
from tap_auth.models import Capability
from tap_boot.orchestrator import BootError, run_boot
from tap_boot.profile import BootProfile, FireCollectorStep, SeedPluginStep

# A real registered collector key, fired with no credentials in these tests by mocking
# the fire op. These are boot-ORCHESTRATOR tests (FireCollectorStep mechanics), not
# domain tests, so the key points at the NEUTRAL grid_fixtures canary collector — the
# test-fixtures plugin present in every profile that runs the core suite (core_dev /
# test_all) — NOT a third-party domain plugin. Pre-resolution only checks the in-memory
# collector registry (get_collector; see orchestrator._resolve_steps — ZERO grid
# mutation), so a registered key is all that's needed; no grid node, no fedramp install.
# Registered as scope:key = plugin-slug:key (register_collector scope is the plugin slug
# since the 2026-07-02 collector-identity refactor).
_TEST_COLLECTOR = "grid_fixtures:canary"


def _profile(*steps, on_failure="abort") -> BootProfile:
    return BootProfile(
        profile_id="test",
        version=1,
        description="test",
        on_failure=on_failure,
        steps=tuple(steps),
    )


class _FakeJob:
    def __init__(self, status: str = "successful", summary: str = "ok") -> None:
        self.status = status
        self.summary = summary


@pytest.mark.django_db
def test_auth_only_standup_syncs_auth():
    run_boot(None)
    assert Capability.objects.exists()
    from django.contrib.auth import get_user_model

    assert get_user_model().objects.filter(tap_builtin_key=BOOTLOADER).exists()


@requires_plugins("computing_core")  # seeds computing_core's GRIFT — needs it installed
@pytest.mark.django_db
def test_seed_population_runs_and_is_idempotent():
    from tap_grid.models import Entity

    profile = _profile(SeedPluginStep(plugin="computing_core", enabled=True))
    run_boot(profile)
    after_first = Entity.objects.count()
    assert after_first > 0
    # Re-applying converges declared state without error (req-boot-idempotent).
    run_boot(profile)
    assert Entity.objects.count() == after_first


@requires_plugins("computing_core")  # uses computing_core as the valid seed alongside the unknown one
@pytest.mark.django_db
def test_unknown_plugin_aborts_before_any_seed():
    from tap_grid.models import Entity

    profile = _profile(
        SeedPluginStep(plugin="computing_core", enabled=True),
        SeedPluginStep(plugin="nonexistent_plugin", enabled=True),
    )
    with pytest.raises(BootError, match="No TAP plugin with slug 'nonexistent_plugin'"):
        run_boot(profile)
    # Pre-resolution fails before ANY seed step runs (collector-node reconcile is a
    # phase prelude, not a step) — so computing_core was NOT seeded. Proof: seeding
    # it now still adds new entities.
    after_abort = Entity.objects.count()
    run_boot(_profile(SeedPluginStep(plugin="computing_core", enabled=True)))
    assert Entity.objects.count() > after_abort


@pytest.mark.django_db
def test_unknown_collector_key_aborts_before_reconcile():
    from tap_cares.models import Collector

    before = Collector.objects.count()
    profile = _profile(FireCollectorStep(key="plugins.nope:missing", enabled=True))
    with pytest.raises(BootError, match="unknown collector key"):
        run_boot(profile)
    # Pre-resolution validates collector keys against the in-memory registry and
    # aborts BEFORE reconcile_collector_nodes() runs — so no Collector grid node
    # was created/updated (req-boot-population-4, the P1 mutation-ordering fix).
    assert Collector.objects.count() == before


@requires_plugins("computing_core")  # needs computing_core installed to reach the bundle check
@pytest.mark.django_db
def test_unknown_bundle_name_aborts():
    # A typo'd bundle must fail loud, not become a green boot with missing data.
    profile = _profile(SeedPluginStep(plugin="computing_core", enabled=True, bundle="no-such-bundle"))
    with pytest.raises(BootError, match="unknown bundle"):
        run_boot(profile)


@pytest.mark.django_db
def test_disabled_unknown_key_does_not_abort():
    # A disabled step is never resolved, so a bogus key behind enabled:false is fine.
    profile = _profile(FireCollectorStep(key="plugins.nope:missing", enabled=False))
    run_boot(profile)  # no raise


@pytest.mark.django_db
def test_fire_collector_step_success(monkeypatch):
    calls = []

    def fake_fire(collector, **kwargs):
        calls.append(kwargs)
        return True, _FakeJob()

    monkeypatch.setattr("tap_cares.services.fire_collector_and_await", fake_fire)
    run_boot(_profile(FireCollectorStep(key=_TEST_COLLECTOR, enabled=True, run_mode="full")))
    assert len(calls) == 1
    assert calls[0]["run_mode"] == "full"
    # No per-step timeout declared -> bootloader default (90s).
    assert calls[0]["timeout_seconds"] == 90.0


@pytest.mark.django_db
def test_fire_collector_step_uses_declared_timeout(monkeypatch):
    calls = []

    def fake_fire(collector, **kwargs):
        calls.append(kwargs)
        return True, _FakeJob()

    monkeypatch.setattr("tap_cares.services.fire_collector_and_await", fake_fire)
    run_boot(_profile(FireCollectorStep(key=_TEST_COLLECTOR, enabled=True, timeout_seconds=222)))
    assert calls[0]["timeout_seconds"] == 222


@pytest.mark.django_db
def test_fire_collector_abort_on_first_failure(monkeypatch):
    calls = []

    def fake_fire(collector, **kwargs):
        calls.append(kwargs)
        return False, _FakeJob(status="failed", summary="boom")

    monkeypatch.setattr("tap_cares.services.fire_collector_and_await", fake_fire)
    profile = _profile(
        FireCollectorStep(key=_TEST_COLLECTOR, enabled=True),
        FireCollectorStep(key=_TEST_COLLECTOR, enabled=True),
        on_failure="abort",
    )
    with pytest.raises(BootError, match="on_failure=abort"):
        run_boot(profile)
    assert len(calls) == 1  # stopped after the first failure


@pytest.mark.django_db
def test_fire_collector_continue_collects_all_failures(monkeypatch):
    calls = []

    def fake_fire(collector, **kwargs):
        calls.append(kwargs)
        return False, _FakeJob(status="failed", summary="boom")

    monkeypatch.setattr("tap_cares.services.fire_collector_and_await", fake_fire)
    profile = _profile(
        FireCollectorStep(key=_TEST_COLLECTOR, enabled=True),
        FireCollectorStep(key=_TEST_COLLECTOR, enabled=True),
        on_failure="continue",
    )
    with pytest.raises(BootError, match="2 failed step"):
        run_boot(profile)
    assert len(calls) == 2  # both attempted under on_failure=continue


@pytest.mark.django_db
def test_echo_receives_progress_lines():
    lines: list[str] = []
    run_boot(None, echo=lines.append)
    assert any("Auth phase" in line for line in lines)
    assert any("auth-only standup complete" in line for line in lines)


class TestBootInvocationSelfCheck:
    """run_boot *detects* out-of-band invocation without blocking it (a tripwire).

    Boot mints the capability system, so it runs *before* any gate exists and cannot be
    capability-gated (the un-gateable-layer variant of spec-service-layer-boundary). The
    confirmed-positive context check walks for a live boot-`BaseCommand` frame (a stable
    Django API, not a forgeable caller flag). But it is deliberately a detection, not a
    wall: a hard fail would brick every boot on any heuristic drift while barely
    inconveniencing a real in-process attacker, so an out-of-band call emits a
    `security`-tagged Flaw (handling `observe_continue`) for incident-response routing
    and boot *proceeds*. `TAP_TEST_MODE` carves the test runner (which drives run_boot
    directly and repeatedly); the whole rest of this suite relies on that carve. These
    tests flip it off to exercise the real production path on both sides — the
    out-of-band tripwire, and the clean allowed-command path.
    """

    @pytest.mark.django_db
    def test_out_of_band_call_flaws_and_proceeds(self, settings, caplog):
        # With the test-runner carve disabled, a bare import-and-call — the exact shape
        # of app or plugin code invoking boot out of band — has no boot-command frame.
        # It must NOT brick boot: a security Flaw is recorded and the standup completes.
        settings.TAP_TEST_MODE = False
        with caplog.at_level(logging.WARNING):
            run_boot(None)

        flaw_records = [r for r in caplog.records if getattr(r, "message_code", None) == "FLAW"]
        assert flaw_records, "expected a FLAW record for the out-of-band boot invocation"
        payload = flaw_records[0].message_data
        assert payload["invariant_id"] == "boot_invoked_out_of_band"
        assert "security" in payload["flaw_tags"]
        assert payload["handling"] == "observe_continue"
        # Detection is a tripwire, not a wall — boot still ran to completion.
        assert Capability.objects.exists()

    @pytest.mark.django_db
    def test_allowed_boot_command_frame_emits_no_flaw(self, settings, caplog):
        settings.TAP_TEST_MODE = False

        class _StandInBootCommand(BaseCommand):
            def run(self) -> None:
                run_boot(None)

        # The check keys on the command class's module, not the file the call sits in:
        # make this stand-in present as the real `manage.py boot` command to the stack
        # walk, exactly as Django leaves the command bound as `self` during execute().
        _StandInBootCommand.__module__ = "tap_boot.management.commands.boot"
        with caplog.at_level(logging.WARNING):
            _StandInBootCommand().run()

        flaw_records = [r for r in caplog.records if getattr(r, "message_code", None) == "FLAW"]
        assert not flaw_records, "an allowed boot command must not trip the tripwire"
        assert Capability.objects.exists()
