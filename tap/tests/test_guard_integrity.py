"""Unit tests for the guard-system integrity guard (`req-dev-validation-meta-integrity-3`).

Proves the detector fires on both tamper shapes it exists to catch — a neutered `check()`
and a removed/renamed guard — because a guard that cannot fail is a false green. The live
tree is covered by `test_guards.py::test_guard_holds`; these drive the mechanism.

The synthetic `check()` bodies are never executed — `_check_is_trivial` reads and parses
their source — so they are written only to have the AST shape under test, kept mypy-clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tap.guards.guard_integrity import GuardIntegrityGuard, _check_is_trivial

# --------------------------------------------------------------------------- #
# _check_is_trivial — the neutered-check() detector
# --------------------------------------------------------------------------- #


class _Pass:
    def check(self) -> None:
        pass


class _ReturnBare:
    def check(self) -> None:
        return


class _ReturnConst:
    def check(self) -> bool:
        return True


class _Ellipsis:
    def check(self) -> None: ...


class _AssertTrue:
    def check(self) -> None:
        assert True


class _DocstringOnly:
    def check(self) -> None:
        """Looks documented, does nothing."""


class _SingleCall:
    def check(self) -> None:
        str(self)  # a real call — does work


class _RealAssert:
    def check(self) -> None:
        assert bool(self)  # non-constant test — not a no-op


class _MultiStatement:
    def check(self) -> None:
        x = 1
        assert x


class _Raises:
    def check(self) -> None:
        raise RuntimeError("not a no-op")


@pytest.mark.parametrize("cls", [_Pass, _ReturnBare, _ReturnConst, _Ellipsis, _AssertTrue, _DocstringOnly])
def test_trivial_bodies_are_flagged(cls: type) -> None:
    assert _check_is_trivial(cls) is True


@pytest.mark.parametrize("cls", [_SingleCall, _RealAssert, _MultiStatement, _Raises])
def test_working_bodies_are_not_flagged(cls: type) -> None:
    assert _check_is_trivial(cls) is False


# --------------------------------------------------------------------------- #
# The guard end-to-end, over a mocked guard set
# --------------------------------------------------------------------------- #


class _Working:
    def check(self) -> None:
        str(self)  # non-trivial body


class _Neutered:
    def check(self) -> None:
        pass  # a disabled guard


def _manifest(tmp_path: Path, *slugs: str) -> Path:
    p = tmp_path / "manifest.txt"
    p.write_text("# test manifest\n" + "\n".join(slugs) + "\n", encoding="utf-8")
    return p


def _guard_with(tmp_path: Path, *slugs: str) -> GuardIntegrityGuard:
    g = GuardIntegrityGuard()
    g.manifest_path = _manifest(tmp_path, *slugs)  # type: ignore[misc]
    return g


def _working(slug: str) -> _Working:
    obj = _Working()
    obj.slug = slug  # type: ignore[attr-defined]
    return obj


def _neutered(slug: str) -> _Neutered:
    obj = _Neutered()
    obj.slug = slug  # type: ignore[attr-defined]
    return obj


def test_passes_when_manifest_matches_and_checks_are_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tap.guards.discover_guards", lambda: [_working("a"), _working("b")])
    _guard_with(tmp_path, "a", "b").check()  # no raise


def test_removed_guard_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tap.guards.discover_guards", lambda: [_working("a")])
    with pytest.raises(AssertionError, match="no longer discovered"):
        _guard_with(tmp_path, "a", "b").check()  # manifest floors "b", which is gone


def test_neutered_check_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tap.guards.discover_guards", lambda: [_working("a"), _neutered("b")])
    with pytest.raises(AssertionError, match="no-op check"):
        _guard_with(tmp_path, "a", "b").check()  # "b" present but gutted
