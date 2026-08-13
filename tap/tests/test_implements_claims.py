"""Tests for implementation claims (`spec-tap-requirement-traceability.md`).

Every detector is exercised against a synthetic tree carrying a *deliberate* violation it
must reject. A guard that cannot fail is a false green — pytest's own `--strict`
deprecation silently reverted for two major versions for exactly this reason.

This module is listed in `spec_trace._CONVENTION_MODULES`, so the claim strings it builds
as fixtures are never mistaken for real claims against the live tree.
"""

from __future__ import annotations

from pathlib import Path

from tap.guards.implements_uniqueness import undeclared_duplicates
from tap.spec_trace import (
    CLAIM_ROLES,
    Claim,
    collect_claims,
    duplicate_claim_groups,
    invalid_claims,
    load_corpus,
    malformed_claims,
    python_scan_roots,
    stale_claims,
)

_TOKEN = "TAP-" + "IMPLEMENTS"

_SPEC = """\
### Alpha
----
RID: `req-example-alpha`
Status: `Implemented`

Alpha derives a fact exactly once.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | --- | --- |
| req-example-alpha-1 | First | Implemented | A testable condition. |
"""


def _tree(tmp_path: Path, modules: dict[str, str]) -> Path:
    (tmp_path / "specs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "specs" / "spec-example.md").write_text(_SPEC, encoding="utf-8")
    pkg = tmp_path / "tap"
    pkg.mkdir(parents=True, exist_ok=True)
    for name, source in modules.items():
        (pkg / name).write_text(source, encoding="utf-8")
    return tmp_path


def _hash_of(tree: Path, rid: str = "req-example-alpha") -> str:
    return load_corpus(tree).requirements[rid].content_hash


def _module(claim: str) -> str:
    return f'def thing():\n    """Does a thing.\n\n    {claim}\n    """\n'


# --- shape ---------------------------------------------------------------------------


def test_well_formed_claim_is_parsed(tmp_path: Path) -> None:
    tree = _tree(tmp_path, {"a.py": ""})
    claim = f"{_TOKEN}: req-example-alpha@{_hash_of(tree)} (derivation) — the one place."
    (tree / "tap" / "a.py").write_text(_module(claim), encoding="utf-8")

    claims, malformed = collect_claims(tree, python_scan_roots(tree))
    assert malformed == []
    assert len(claims) == 1
    assert (claims[0].rid, claims[0].role, claims[0].qualname) == (
        "req-example-alpha",
        "derivation",
        "thing",
    )


def test_near_miss_fails_closed(tmp_path: Path) -> None:
    """A misspelled tag must FAIL, not be skipped — the clippy `SAFTEY:` hole."""
    tree = _tree(tmp_path, {"a.py": _module("TAP-IMPLEMENT: req-example-alpha (derivation)")})
    offenders = malformed_claims(tree)
    assert len(offenders) == 1
    assert "TAP-IMPLEMENT:" in offenders[0].text


def test_claim_missing_its_hash_is_malformed(tmp_path: Path) -> None:
    tree = _tree(tmp_path, {"a.py": _module(f"{_TOKEN}: req-example-alpha (derivation) — no hash.")})
    assert len(malformed_claims(tree)) == 1


# --- integrity -----------------------------------------------------------------------


def test_claim_on_unknown_requirement_is_invalid(tmp_path: Path) -> None:
    tree = _tree(tmp_path, {"a.py": ""})
    claim = f"{_TOKEN}: req-absent-thing@{'0' * 12} (derivation) — nope."
    (tree / "tap" / "a.py").write_text(_module(claim), encoding="utf-8")

    problems = invalid_claims(tree)
    assert len(problems) == 1
    assert "does not exist" in problems[0][1]


def test_claim_with_unknown_role_is_invalid(tmp_path: Path) -> None:
    tree = _tree(tmp_path, {"a.py": ""})
    claim = f"{_TOKEN}: req-example-alpha@{_hash_of(tree)} (invented) — bad role."
    (tree / "tap" / "a.py").write_text(_module(claim), encoding="utf-8")

    problems = invalid_claims(tree)
    assert len(problems) == 1
    assert "not one of" in problems[0][1]


def test_role_vocabulary_is_closed() -> None:
    assert CLAIM_ROLES == {"derivation", "enforcement", "surface"}


# --- uniqueness ----------------------------------------------------------------------


def test_duplicate_claim_across_modules_is_detected(tmp_path: Path) -> None:
    """One requirement-and-role, two modules — the anti-pattern this convention targets."""
    tree = _tree(tmp_path, {"a.py": "", "b.py": ""})
    claim = f"{_TOKEN}: req-example-alpha@{_hash_of(tree)} (derivation) — mine."
    for name in ("a.py", "b.py"):
        (tree / "tap" / name).write_text(_module(claim), encoding="utf-8")

    duplicates = duplicate_claim_groups(tree)
    assert list(duplicates) == [("req-example-alpha", "derivation")]
    assert len(duplicates[("req-example-alpha", "derivation")]) == 2


def test_same_requirement_different_roles_is_not_a_duplicate(tmp_path: Path) -> None:
    """A requirement realized at two layers is legitimate — that is why roles exist."""
    tree = _tree(tmp_path, {"a.py": "", "b.py": ""})
    digest = _hash_of(tree)
    (tree / "tap" / "a.py").write_text(
        _module(f"{_TOKEN}: req-example-alpha@{digest} (derivation) — computes it."), encoding="utf-8"
    )
    (tree / "tap" / "b.py").write_text(
        _module(f"{_TOKEN}: req-example-alpha@{digest} (enforcement) — guards it."), encoding="utf-8"
    )
    assert duplicate_claim_groups(tree) == {}


def test_repeated_claim_within_one_module_is_not_a_duplicate(tmp_path: Path) -> None:
    """Conditional definitions declare the same claim twice in one file, legitimately."""
    tree = _tree(tmp_path, {"a.py": ""})
    claim = f"{_TOKEN}: req-example-alpha@{_hash_of(tree)} (derivation) — mine."
    (tree / "tap" / "a.py").write_text(_module(claim) + "\n\n" + _module(claim), encoding="utf-8")
    assert duplicate_claim_groups(tree) == {}


def _claim_at(tmp_path: Path, module: str) -> Claim:
    return Claim(
        rid="req-example-alpha",
        recorded_hash="0" * 12,
        role="derivation",
        qualname="thing",
        path=tmp_path / module,
        lineno=1,
    )


def test_duplicate_is_permitted_when_both_sites_share_a_known_dupe_group(tmp_path: Path) -> None:
    duplicates = {("req-example-alpha", "derivation"): [_claim_at(tmp_path, "a.py"), _claim_at(tmp_path, "b.py")]}
    tagged = {"a.py": {"shared-group"}, "b.py": {"shared-group"}}
    assert undeclared_duplicates(duplicates, tagged, tmp_path) == []


def test_duplicate_still_fails_when_the_groups_differ(tmp_path: Path) -> None:
    """Two unrelated exemptions that happen to coincide are not a declaration about this pair."""
    duplicates = {("req-example-alpha", "derivation"): [_claim_at(tmp_path, "a.py"), _claim_at(tmp_path, "b.py")]}
    tagged = {"a.py": {"group-one"}, "b.py": {"group-two"}}
    assert len(undeclared_duplicates(duplicates, tagged, tmp_path)) == 1


def test_duplicate_fails_when_only_one_site_is_tagged(tmp_path: Path) -> None:
    duplicates = {("req-example-alpha", "derivation"): [_claim_at(tmp_path, "a.py"), _claim_at(tmp_path, "b.py")]}
    assert len(undeclared_duplicates(duplicates, {"a.py": {"shared-group"}}, tmp_path)) == 1


# --- staleness -----------------------------------------------------------------------


def test_stale_claim_is_detected_after_the_requirement_changes(tmp_path: Path) -> None:
    tree = _tree(tmp_path, {"a.py": ""})
    claim = f"{_TOKEN}: req-example-alpha@{_hash_of(tree)} (derivation) — mine."
    (tree / "tap" / "a.py").write_text(_module(claim), encoding="utf-8")
    assert stale_claims(tree) == []

    spec = tree / "specs" / "spec-example.md"
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "Alpha derives a fact exactly once.", "Alpha derives a materially different fact."
        ),
        encoding="utf-8",
    )

    stale = stale_claims(tree)
    assert len(stale) == 1
    assert stale[0][1] == _hash_of(tree)  # the expected hash is the requirement's new one


def test_status_change_does_not_stale_a_claim(tmp_path: Path) -> None:
    """Status is derived and moves on its own lifecycle — it must not churn every claim."""
    tree = _tree(tmp_path, {"a.py": ""})
    claim = f"{_TOKEN}: req-example-alpha@{_hash_of(tree)} (derivation) — mine."
    (tree / "tap" / "a.py").write_text(_module(claim), encoding="utf-8")

    spec = tree / "specs" / "spec-example.md"
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("Status: `Implemented`", "Status: `Verified`"),
        encoding="utf-8",
    )
    assert stale_claims(tree) == []


def test_claim_on_missing_requirement_is_not_double_reported(tmp_path: Path) -> None:
    """A dangling claim is an integrity finding; reporting it as stale too would double-count."""
    tree = _tree(tmp_path, {"a.py": ""})
    claim = f"{_TOKEN}: req-absent-thing@{'0' * 12} (derivation) — nope."
    (tree / "tap" / "a.py").write_text(_module(claim), encoding="utf-8")

    assert stale_claims(tree) == []
    assert len(invalid_claims(tree)) == 1
