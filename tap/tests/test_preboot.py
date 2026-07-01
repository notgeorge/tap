"""Unit tests for the settings-free pre-boot stage (tap/preboot.py).

These test the pre-Django kernel directly — variable resolution, the plain-JSON
profile reader, uv-install arg building + idempotency, entry-point discovery +
identity check, and the static coherence guard. No Django DB is needed; the one
test that touches settings only reads INSTALLED_APPS to keep the build-baked
transition set honest.

Spec: specs/spec-tap-boot-v0.md (req-boot-preboot, req-boot-install-section,
req-boot-variable-resolution, req-boot-snapshot).
"""

from __future__ import annotations

import pytest

from tap import preboot

# --- Variable resolution (req-boot-variable-resolution) ----------------------


def test_env_var_name_mapping() -> None:
    assert preboot.env_var_name("install", "snapshot_before_migrate") == ("TAP_BOOT_INSTALL__SNAPSHOT_BEFORE_MIGRATE")


def test_resolve_var_precedence_env_over_profile_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    section = {"snapshot_before_migrate": True}
    # default wins when neither env nor profile present
    monkeypatch.delenv("TAP_BOOT_INSTALL__SNAPSHOT_BEFORE_MIGRATE", raising=False)
    r = preboot.resolve_var("install", "missing_key", profile_section=section, default=False, is_bool=True)
    assert (r.value, r.source) == (False, "default")
    # profile wins over default
    r = preboot.resolve_var("install", "snapshot_before_migrate", profile_section=section, default=False, is_bool=True)
    assert (r.value, r.source) == (True, "profile")
    # env wins over profile
    monkeypatch.setenv("TAP_BOOT_INSTALL__SNAPSHOT_BEFORE_MIGRATE", "false")
    r = preboot.resolve_var("install", "snapshot_before_migrate", profile_section=section, default=False, is_bool=True)
    assert (r.value, r.source) == (False, "env")


def test_resolve_var_empty_env_treated_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # docker-compose materializes an unmapped ${VAR:-} as "" — must NOT read as False.
    monkeypatch.setenv("TAP_BOOT_INSTALL__SNAPSHOT_BEFORE_MIGRATE", "")
    r = preboot.resolve_var("install", "snapshot_before_migrate", profile_section={}, default=True, is_bool=True)
    assert (r.value, r.source) == (True, "default")


@pytest.mark.parametrize(
    "raw,expected", [("true", True), ("1", True), ("on", True), ("false", False), ("no", False), ("0", False)]
)
def test_bool_coercion(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv("TAP_BOOT_INSTALL__SNAPSHOT_BEFORE_MIGRATE", raw)
    r = preboot.resolve_var("install", "snapshot_before_migrate", profile_section=None, default=None, is_bool=True)
    assert r.value is expected


# --- Install arg building + idempotency (req-boot-install-section, -preboot-3) --


def test_dist_name_for_slug() -> None:
    assert preboot.dist_name_for_slug("genericom") == "tap-plugin-genericom"
    assert preboot.dist_name_for_slug("aws_core") == "tap-plugin-aws-core"


def test_uv_install_args_git() -> None:
    entry = {"slug": "genericom", "source": {"type": "git", "url": "https://x/y.git", "rev": "abc123"}}
    args = preboot.uv_install_args(entry)
    assert args == ["uv", "pip", "install", "tap-plugin-genericom @ git+https://x/y.git@abc123"]


def test_uv_install_args_editable() -> None:
    entry = {"slug": "genericom", "source": {"type": "editable", "path": "plugins/genericom"}}
    args = preboot.uv_install_args(entry)
    assert args[:4] == ["uv", "pip", "install", "--editable"]
    assert args[4].endswith("plugins/genericom")


def test_uv_install_args_unknown_source_raises() -> None:
    entry = {"slug": "x", "source": {"type": "svn"}}
    with pytest.raises(preboot.PrebootError):
        preboot.uv_install_args(entry)


# --- Profile reading (req-boot-install-section-2) ----------------------------


def test_read_profile_missing_raises() -> None:
    with pytest.raises(preboot.PrebootError):
        preboot.read_profile("does-not-exist-profile")


def test_read_genericom_install_profile() -> None:
    profile = preboot.read_profile("genericom-install")
    entries = preboot.install_plugin_specs(profile)
    assert [e["slug"] for e in entries] == ["genericom"]
    assert entries[0]["source"]["type"] == "editable"


def test_install_plugin_specs_filters_disabled() -> None:
    profile = {
        "install": {
            "plugins": [
                {"slug": "a", "enabled": True, "source": {"type": "path", "path": "p"}},
                {"slug": "b", "enabled": False, "source": {"type": "path", "path": "p"}},
            ]
        }
    }
    assert [e["slug"] for e in preboot.install_plugin_specs(profile)] == ["a"]


def test_population_seed_slugs_filters_type_and_enabled() -> None:
    profile = {
        "population": {
            "steps": [
                {"type": "seed-plugin", "plugin": "a", "enabled": True},
                {"type": "seed-plugin", "plugin": "b", "enabled": False},
                {"type": "fire-collector", "key": "k", "enabled": True},
            ]
        }
    }
    assert preboot.population_seed_slugs(profile) == ["a"]


# --- Entry-point discovery identity check (req-boot-preboot) ------------------


def test_resolve_tap_plugins_identity_mismatch_raises() -> None:
    entries = [{"slug": "genericom", "source": {"type": "path", "path": "p"}}]
    # discovered has a DIFFERENT key than the declared slug
    with pytest.raises(preboot.PrebootError, match="identity mismatch"):
        preboot.resolve_tap_plugins(entries, {"other": "other.apps.OtherConfig"})


def test_resolve_tap_plugins_happy() -> None:
    entries = [{"slug": "genericom", "source": {"type": "path", "path": "p"}}]
    got = preboot.resolve_tap_plugins(entries, {"genericom": "genericom.apps.GenericomConfig"})
    assert got == ["genericom.apps.GenericomConfig"]


# --- Static coherence guard (req-boot-install-section-3) ----------------------


def test_static_coherence_guard_passes_for_build_baked() -> None:
    # a build-baked slug in population, absent from install, must pass
    profile = {"population": {"steps": [{"type": "seed-plugin", "plugin": "samsite", "enabled": True}]}}
    preboot.static_coherence_guard(profile, install_slugs=set())  # no raise


def test_static_coherence_guard_passes_for_installed() -> None:
    profile = {"population": {"steps": [{"type": "seed-plugin", "plugin": "genericom", "enabled": True}]}}
    preboot.static_coherence_guard(profile, install_slugs={"genericom"})  # no raise


def test_static_coherence_guard_fails_for_unknown() -> None:
    profile = {"population": {"steps": [{"type": "seed-plugin", "plugin": "typo_plugin", "enabled": True}]}}
    with pytest.raises(preboot.PrebootError, match="static coherence guard"):
        preboot.static_coherence_guard(profile, install_slugs={"genericom"})


# --- Build-baked transition set stays honest against settings ----------------


def test_build_baked_matches_installed_apps() -> None:
    """BUILD_BAKED_PLUGIN_SLUGS must equal the plugins hardcoded in INSTALLED_APPS.

    Keeps the transition constant from silently drifting as plugins migrate to
    package-mode (a stale entry would make the coherence guard wave through an
    uninstalled slug). genericom is package-mode, so it is intentionally absent.
    """
    from django.conf import settings

    hardcoded = {
        app.split(".")[1] for app in settings.INSTALLED_APPS if app.startswith("plugins.") and app.endswith("Config")
    }
    assert preboot.BUILD_BAKED_PLUGIN_SLUGS == hardcoded
