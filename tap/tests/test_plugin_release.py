"""Unit tests for tap.plugin_release (req-dev-workspace-release).

Pure-function coverage of tag normalization + the consuming-profile rev bump: no git,
network, or Django. The live push/tag steps live in scripts/release-plugin.sh and are
exercised by hand during the eviction wave.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tap.plugin_release import (
    PluginReleaseError,
    ProfileBump,
    bump_profiles,
    find_consumers,
    normalize_tag,
)


def _write_profile(boot_dir: Path, name: str, plugins: list[dict[str, Any]]) -> Path:
    path = boot_dir / f"{name}.boot.json"
    path.write_text(
        json.dumps({"version": 1, "description": name, "install": {"plugins": plugins}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _git(slug: str, rev: str, *, note: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "slug": slug,
        "enabled": True,
        "source": {
            "type": "git",
            "url": f"https://github.com/unified-systems-com/tap-plugin-{slug.replace('_', '-')}",
            "rev": rev,
            "credential": "github-plugins-ro",
        },
    }
    if note is not None:
        entry["note"] = note
    return entry


def _editable(slug: str) -> dict[str, Any]:
    return {"slug": slug, "enabled": True, "source": {"type": "editable", "path": f"plugins/{slug}"}}


# --------------------------------------------------------------------------- normalize_tag


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.2.0", "v0.2.0"),
        ("v0.2.0", "v0.2.0"),
        ("1.10.3", "v1.10.3"),
        ("0.2.0-rc1", "v0.2.0-rc1"),
        ("v2.0.0+build.5", "v2.0.0+build.5"),
    ],
)
def test_normalize_tag_accepts_and_canonicalizes(raw: str, expected: str) -> None:
    assert normalize_tag(raw) == expected


@pytest.mark.parametrize("raw", ["0.2", "v0", "1.2.3.4", "latest", "", "v0.2.0 ", "0.2.0a"])
def test_normalize_tag_rejects_malformed(raw: str) -> None:
    with pytest.raises(PluginReleaseError):
        normalize_tag(raw)


# --------------------------------------------------------------------------- bump_profiles


def test_bumps_only_the_named_slug_in_git_entries(tmp_path: Path) -> None:
    _write_profile(tmp_path, "samsite", [_git("compliance_core", "v0.1.0"), _git("fedramp_20x_ksi", "v0.2.0")])
    bumps = bump_profiles(tmp_path, "compliance_core", "v0.2.0")

    assert [b.old_rev for b in bumps] == ["v0.1.0"]
    written = json.loads((tmp_path / "samsite.boot.json").read_text())
    by_slug = {p["slug"]: p for p in written["install"]["plugins"]}
    assert by_slug["compliance_core"]["source"]["rev"] == "v0.2.0"
    assert by_slug["fedramp_20x_ksi"]["source"]["rev"] == "v0.2.0"  # untouched


def test_bumps_across_multiple_profiles(tmp_path: Path) -> None:
    _write_profile(tmp_path, "samsite", [_git("compliance_core", "v0.1.0")])
    _write_profile(tmp_path, "operator_sso", [_git("compliance_core", "v0.1.0")])
    bumps = bump_profiles(tmp_path, "compliance_core", "v0.2.0")
    assert {b.path.name for b in bumps} == {"samsite.boot.json", "operator_sso.boot.json"}
    for name in ("samsite", "operator_sso"):
        written = json.loads((tmp_path / f"{name}.boot.json").read_text())
        assert written["install"]["plugins"][0]["source"]["rev"] == "v0.2.0"


def test_already_at_tag_is_a_noop(tmp_path: Path) -> None:
    _write_profile(tmp_path, "samsite", [_git("compliance_core", "v0.2.0")])
    assert bump_profiles(tmp_path, "compliance_core", "v0.2.0") == []


def test_editable_entry_is_not_bumped(tmp_path: Path) -> None:
    _write_profile(tmp_path, "test_all", [_editable("compliance_core")])
    assert bump_profiles(tmp_path, "compliance_core", "v0.2.0") == []
    written = json.loads((tmp_path / "test_all.boot.json").read_text())
    assert written["install"]["plugins"][0]["source"] == {"type": "editable", "path": "plugins/compliance_core"}


def test_refreshes_tag_in_note_prose(tmp_path: Path) -> None:
    note = "Git-sourced from its own repo at v0.1.0 via the github-plugins-ro PAT."
    _write_profile(tmp_path, "samsite", [_git("compliance_core", "v0.1.0", note=note)])
    bump_profiles(tmp_path, "compliance_core", "v0.2.0")
    written = json.loads((tmp_path / "samsite.boot.json").read_text())
    assert "at v0.2.0 via" in written["install"]["plugins"][0]["note"]
    assert "v0.1.0" not in written["install"]["plugins"][0]["note"]


def test_note_refresh_does_not_touch_unrelated_versions(tmp_path: Path) -> None:
    # Only the entry's own old rev token is swapped; a different version mentioned in prose stays.
    note = "Pinned at v0.1.0; compatible with core v0.1.5."
    _write_profile(tmp_path, "samsite", [_git("compliance_core", "v0.1.0", note=note)])
    bump_profiles(tmp_path, "compliance_core", "v0.2.0")
    written = json.loads((tmp_path / "samsite.boot.json").read_text())
    assert "core v0.1.5" in written["install"]["plugins"][0]["note"]
    assert "Pinned at v0.2.0;" in written["install"]["plugins"][0]["note"]


def test_dry_run_computes_but_does_not_write(tmp_path: Path) -> None:
    path = _write_profile(tmp_path, "samsite", [_git("compliance_core", "v0.1.0")])
    before = path.read_text()
    bumps = bump_profiles(tmp_path, "compliance_core", "v0.2.0", dry_run=True)
    assert bumps == [ProfileBump(path=path, slug="compliance_core", old_rev="v0.1.0", new_rev="v0.2.0")]
    assert path.read_text() == before  # untouched on disk


def test_no_consumer_returns_empty(tmp_path: Path) -> None:
    _write_profile(tmp_path, "samsite", [_git("other_plugin", "v0.1.0")])
    assert bump_profiles(tmp_path, "compliance_core", "v0.2.0") == []


def test_malformed_profile_raises(tmp_path: Path) -> None:
    (tmp_path / "broken.boot.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PluginReleaseError, match="cannot read boot profile"):
        bump_profiles(tmp_path, "compliance_core", "v0.2.0")


# --------------------------------------------------------------------------- find_consumers


def test_find_consumers_lists_only_git_sourced(tmp_path: Path) -> None:
    _write_profile(tmp_path, "samsite", [_git("compliance_core", "v0.1.0")])
    _write_profile(tmp_path, "test_all", [_editable("compliance_core")])
    _write_profile(tmp_path, "soak", [_git("other", "v0.1.0")])
    consumers = find_consumers(tmp_path, "compliance_core")
    assert [p.name for p in consumers] == ["samsite.boot.json"]
