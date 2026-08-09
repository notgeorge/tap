"""Boot-profile load / schema-validate / parse (req-boot-profile)."""

from __future__ import annotations

import json

import pytest

from tap_boot.profile import (
    BootProfileError,
    FireCollectorStep,
    SeedPluginStep,
    load_profile,
)


def _write(boot_dir, profile_id: str, data: dict[str, object]) -> None:
    (boot_dir / f"{profile_id}.boot.json").write_text(json.dumps(data))


@pytest.fixture
def boot_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("tap_boot.profile.boot_dir", lambda: tmp_path)
    return tmp_path


def test_load_real_samsite_profile_parses_steps():
    profile = load_profile("samsite")
    assert profile.version == 1
    assert profile.on_failure == "abort"
    seeds = [s for s in profile.steps if isinstance(s, SeedPluginStep)]
    fires = [s for s in profile.steps if isinstance(s, FireCollectorStep)]
    assert len(seeds) == 6
    assert len(fires) == 4
    # Declared order is preserved: all seeds precede all fires in samsite.
    assert profile.steps[:6] == tuple(seeds)
    assert profile.has_population


def test_test_all_profile_is_seed_only():
    profile = load_profile("test_all")
    assert all(isinstance(s, SeedPluginStep) for s in profile.steps)
    assert profile.has_population


def test_missing_profile_raises(boot_dir):
    with pytest.raises(BootProfileError, match="not found"):
        load_profile("does-not-exist")


def test_enabled_steps_filters_disabled(boot_dir):
    _write(
        boot_dir,
        "p",
        {
            "version": 1,
            "population": {
                "steps": [
                    {"type": "seed-plugin", "plugin": "a", "enabled": True},
                    {"type": "seed-plugin", "plugin": "b", "enabled": False},
                ]
            },
        },
    )
    profile = load_profile("p")
    assert len(profile.steps) == 2
    assert [s.plugin for s in profile.enabled_steps if isinstance(s, SeedPluginStep)] == ["a"]


def test_on_failure_defaults_to_abort(boot_dir):
    _write(boot_dir, "p", {"version": 1, "population": {"steps": []}})
    assert load_profile("p").on_failure == "abort"


def test_collector_preflight_parses_and_defaults_to_undeclared(boot_dir):
    # Undeclared -> None (the orchestrator's variable ladder then defaults it true,
    # req-boot-obs-preflight-4); a declared false parses through.
    _write(boot_dir, "p", {"version": 1, "population": {"steps": []}})
    assert load_profile("p").collector_preflight is None
    _write(boot_dir, "q", {"version": 1, "population": {"collector_preflight": False, "steps": []}})
    assert load_profile("q").collector_preflight is False


def test_no_population_is_auth_only(boot_dir):
    _write(boot_dir, "p", {"version": 1})
    profile = load_profile("p")
    assert not profile.has_population
    assert profile.steps == ()


def test_schema_rejects_unknown_field(boot_dir):
    _write(
        boot_dir,
        "bad",
        {
            "version": 1,
            "population": {"steps": [{"type": "seed-plugin", "plugin": "a", "enabled": True, "bogus": 1}]},
        },
    )
    with pytest.raises(BootProfileError, match="schema validation"):
        load_profile("bad")


def test_schema_rejects_wrong_version(boot_dir):
    _write(boot_dir, "bad", {"version": 0, "population": {"steps": []}})
    with pytest.raises(BootProfileError, match="schema validation"):
        load_profile("bad")


def test_schema_rejects_bad_step_type(boot_dir):
    _write(
        boot_dir,
        "bad",
        {"version": 1, "population": {"steps": [{"type": "frobnicate", "enabled": True}]}},
    )
    with pytest.raises(BootProfileError, match="schema validation"):
        load_profile("bad")
