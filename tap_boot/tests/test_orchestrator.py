"""run_boot orchestration: auth → population, pre-resolution, on_failure (req-boot-phases/population).

These are fresh-test-DB integration tests — pytest-django builds the DB and the
session `sync_auth` baseline runs first; each `run_boot` then converges it again.
"""

from __future__ import annotations

import pytest

from tap_auth.actors import BOOTLOADER
from tap_auth.models import Capability
from tap_boot.orchestrator import BootError, run_boot
from tap_boot.profile import BootProfile, FireCollectorStep, SeedPluginStep

# A real registered collector key, fired with no credentials in these tests by
# mocking the fire op — pre-resolution still resolves it against the grid node
# that the population phase reconciles.
_KSI_COLLECTOR = "fedramp_20x_ksi:ksi-catalog"


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
    run_boot(_profile(FireCollectorStep(key=_KSI_COLLECTOR, enabled=True, run_mode="full")))
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
    run_boot(_profile(FireCollectorStep(key=_KSI_COLLECTOR, enabled=True, timeout_seconds=222)))
    assert calls[0]["timeout_seconds"] == 222


@pytest.mark.django_db
def test_fire_collector_abort_on_first_failure(monkeypatch):
    calls = []

    def fake_fire(collector, **kwargs):
        calls.append(kwargs)
        return False, _FakeJob(status="failed", summary="boom")

    monkeypatch.setattr("tap_cares.services.fire_collector_and_await", fake_fire)
    profile = _profile(
        FireCollectorStep(key=_KSI_COLLECTOR, enabled=True),
        FireCollectorStep(key=_KSI_COLLECTOR, enabled=True),
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
        FireCollectorStep(key=_KSI_COLLECTOR, enabled=True),
        FireCollectorStep(key=_KSI_COLLECTOR, enabled=True),
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
