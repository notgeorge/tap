"""Unit tests for tap.dev_workspace.derive_profile (req-dev-workspace-spawn).

Pure-function coverage of the profile derivation: the slug is a selector into the base
profile's install list, and the git entry's url/rev/credential are the clone authority.
No network — the actual clone (clone_editable) is exercised by a separate host smoke.
"""

from __future__ import annotations

from typing import Any

import pytest

from tap.dev_workspace import DevWorkspaceError, derive_profile


def _profile(*plugins: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "description": "base", "install": {"plugins": list(plugins)}}


def _git(slug: str, rev: str = "v0.1.0") -> dict[str, Any]:
    return {
        "slug": slug,
        "enabled": True,
        "source": {
            "type": "git",
            "url": f"https://github.com/notgeorge/tap-plugin-{slug.replace('_', '-')}",
            "rev": rev,
            "credential": "github-plugins-ro",
        },
    }


def _editable(slug: str) -> dict[str, Any]:
    return {"slug": slug, "enabled": True, "source": {"type": "editable", "path": f"plugins/{slug}"}}


def test_flips_git_to_editable_and_returns_clone_spec() -> None:
    base = _profile(_git("compliance_core"), _git("fedramp_20x_ksi", rev="v0.2.0"))
    derived, specs = derive_profile(base, ["compliance_core"])

    # only the named slug is flipped
    by_slug = {p["slug"]: p for p in derived["install"]["plugins"]}
    assert by_slug["compliance_core"]["source"] == {"type": "editable", "path": "_dev-plugins/compliance_core"}
    assert by_slug["fedramp_20x_ksi"]["source"]["type"] == "git"

    assert len(specs) == 1
    spec = specs[0]
    assert spec.slug == "compliance_core"
    assert spec.url.endswith("tap-plugin-compliance-core")
    assert spec.rev == "v0.1.0"
    assert spec.credential == "github-plugins-ro"


def test_coupled_flips_both() -> None:
    base = _profile(_git("compliance_core"), _git("fedramp_20x_ksi"))
    derived, specs = derive_profile(base, ["compliance_core", "fedramp_20x_ksi"])
    assert {s.slug for s in specs} == {"compliance_core", "fedramp_20x_ksi"}
    assert all(p["source"]["type"] == "editable" for p in derived["install"]["plugins"])


def test_slug_not_in_profile_raises() -> None:
    base = _profile(_git("compliance_core"))
    with pytest.raises(DevWorkspaceError, match="not a plugin in the base profile"):
        derive_profile(base, ["nonexistent"])


def test_already_editable_is_left_as_is_and_not_cloned() -> None:
    base = _profile(_editable("grid_fixtures"))
    derived, specs = derive_profile(base, ["grid_fixtures"])
    assert specs == []  # nothing to clone
    assert derived["install"]["plugins"][0]["source"] == {"type": "editable", "path": "plugins/grid_fixtures"}


def test_non_git_non_editable_source_raises() -> None:
    base = _profile({"slug": "x", "source": {"type": "wheelhouse", "version": "0.1.0"}})
    with pytest.raises(DevWorkspaceError, match="expected 'git'"):
        derive_profile(base, ["x"])


def test_git_missing_rev_raises() -> None:
    base = _profile({"slug": "x", "source": {"type": "git", "url": "https://example/x"}})
    with pytest.raises(DevWorkspaceError, match="missing url/rev"):
        derive_profile(base, ["x"])


def test_does_not_mutate_the_input_profile() -> None:
    base = _profile(_git("compliance_core"))
    derive_profile(base, ["compliance_core"])
    # the original entry is untouched (deep copy)
    assert base["install"]["plugins"][0]["source"]["type"] == "git"
