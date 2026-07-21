"""Unit tests for the direct-write scanner (`req-tap-auth-policy-9` Rule B).

Hermetic and Django-free: the scanner takes its managed-model index as an argument,
so these drive it over synthetic source with a synthetic index — no app registry, no
DB. Two behaviours are load-bearing here and were previously untested at the unit
level (the scanner was only exercised live through `test_guards.py`):

* **Name resolution** (`req-tap-auth-policy-9-name-resolution`) — a write on a class
  name a *non-managed* model also bears is resolved through the file's imports, not
  flagged by the bare string. The regression is real: `tap_auth.User` was flagged only
  because `computing_core.User` shares the name.
* **Exemption freshness** (`req-tap-auth-policy-9-unused-exemption`) — a
  `# TAP-WRITE-COV` comment that suppresses no flagged write is surfaced as stale.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tap.direct_write_coverage import (
    CollisionResolution,
    ManagedModelIndex,
    scan_direct_writes,
)
from tap.source_scan import build_import_bindings

# `User` is the real-world collision: a graph-managed `computing_core.User` and a
# non-managed `tap_auth.User`. `Batch` stands in for the unambiguous majority — a
# managed name no other model bears, so it needs no resolution.
_INDEX = ManagedModelIndex(
    names=frozenset({"User", "Batch"}),
    collisions={
        "User": CollisionResolution(
            managed_roots=frozenset({"tap_plugin.computing_core"}),
            nonmanaged_roots=frozenset({"tap_auth"}),
        )
    },
)


def _scan(tmp_path: Path, source: str) -> object:
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    return scan_direct_writes([tmp_path], _INDEX)


def _flagged(result: object) -> set[tuple[str, str]]:
    return {(s.model, s.op) for s in result.direct_writes}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Name resolution — the collision fix
# --------------------------------------------------------------------------- #


def test_nonmanaged_collision_write_is_not_flagged(tmp_path: Path) -> None:
    """A write on the NON-managed `tap_auth.User` resolves away — the false positive."""
    result = _scan(tmp_path, "from tap_auth.models import User\n\n\ndef f():\n    User.objects.get_or_create(x=1)\n")
    assert _flagged(result) == set()
    assert result.exempt_skipped == []  # type: ignore[attr-defined]


def test_managed_collision_write_is_flagged(tmp_path: Path) -> None:
    """A write on the graph-managed `computing_core.User` stays flagged."""
    result = _scan(
        tmp_path,
        "from tap_plugin.computing_core.models import User\n\n\ndef f():\n    User.objects.create(x=1)\n",
    )
    assert _flagged(result) == {("User", "create")}


def test_managed_collision_via_reexport_prefix_is_flagged(tmp_path: Path) -> None:
    """Re-export (`.models` not the defining `.models.user`) still resolves under the app root."""
    result = _scan(
        tmp_path,
        "from tap_plugin.computing_core.models import User\n\n\ndef f():\n    User(x=1).save()\n",
    )
    assert _flagged(result) == {("User", "save")}


def test_unresolved_collision_write_fails_closed(tmp_path: Path) -> None:
    """A collision name with no resolvable import (bare use) stays flagged — fail-closed."""
    result = _scan(tmp_path, "def f():\n    User.objects.create(x=1)\n")
    assert _flagged(result) == {("User", "create")}


def test_star_import_collision_fails_closed(tmp_path: Path) -> None:
    """A star import leaves the origin unknown, so the collision write stays flagged."""
    result = _scan(tmp_path, "from elsewhere import *\n\n\ndef f():\n    User.objects.create(x=1)\n")
    assert _flagged(result) == {("User", "create")}


def test_noncolliding_managed_name_flagged_regardless_of_import(tmp_path: Path) -> None:
    """An unambiguous managed name is bare-matched — resolution never runs (no regression)."""
    result = _scan(tmp_path, "from anywhere import Batch\n\n\ndef f():\n    Batch.objects.create(x=1)\n")
    assert _flagged(result) == {("Batch", "create")}


def test_queryset_terminal_write_on_managed_collision_is_flagged(tmp_path: Path) -> None:
    """`<Model>.objects.filter(...).delete()` resolves through the chain to the managed owner."""
    result = _scan(
        tmp_path,
        "from tap_plugin.computing_core.models import User\n\n\ndef f():\n    User.objects.filter(x=1).delete()\n",
    )
    assert _flagged(result) == {("User", "delete")}


# --------------------------------------------------------------------------- #
# Exemption freshness — the unused-suppression detector
# --------------------------------------------------------------------------- #


def test_exemption_on_a_flagged_write_is_used(tmp_path: Path) -> None:
    src = (
        "from tap_plugin.computing_core.models import User\n\n\n"
        "def f():\n    User.objects.create(  # TAP-WRITE-COV: sanctioned\n        x=1,\n    )\n"
    )
    result = _scan(tmp_path, src)
    assert _flagged(result) == set()
    assert [(s.model, s.op) for s in result.exempt_skipped] == [("User", "create")]  # type: ignore[attr-defined]
    assert result.unused_exemptions == []  # type: ignore[attr-defined]


def test_orphaned_exemption_is_surfaced(tmp_path: Path) -> None:
    """A `# TAP-WRITE-COV` on no flagged write is stale."""
    result = _scan(tmp_path, "x = 1  # TAP-WRITE-COV: nothing here\n")
    assert [c.lineno for c in result.unused_exemptions] == [1]  # type: ignore[attr-defined]


def test_resolved_away_write_orphans_its_exemption(tmp_path: Path) -> None:
    """The exact 2026-07 incident: the write resolves out of scope (`tap_auth.User`), so
    its still-present `# TAP-WRITE-COV` comment suppresses nothing and is surfaced."""
    src = (
        "from tap_auth.models import User\n\n\n"
        "def f():\n    User.objects.get_or_create(  # TAP-WRITE-COV: was covering this\n        x=1,\n    )\n"
    )
    result = _scan(tmp_path, src)
    assert _flagged(result) == set()
    assert result.exempt_skipped == []  # type: ignore[attr-defined]
    assert [c.lineno for c in result.unused_exemptions] == [5]  # type: ignore[attr-defined]


def test_marker_inside_a_string_is_not_an_exemption(tmp_path: Path) -> None:
    """The marker in a string literal (a hint, a docstring) is not a live comment."""
    result = _scan(tmp_path, 'HINT = "annotate a sanctioned write with # TAP-WRITE-COV: <reason>"\n')
    assert result.unused_exemptions == []  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# The import binder (`tap.source_scan.build_import_bindings`)
# --------------------------------------------------------------------------- #


def _origin(source: str, expr: str) -> str | None:
    bindings = build_import_bindings(ast.parse(source))
    return bindings.resolve(ast.parse(expr, mode="eval").body)


def test_binder_from_import() -> None:
    assert _origin("from a.b import C", "C") == "a.b.C"


def test_binder_aliased_symbol() -> None:
    assert _origin("from a.b import C as D", "D") == "a.b.C"


def test_binder_module_alias_attribute() -> None:
    assert _origin("import a.b.c as x", "x.User") == "a.b.c.User"


def test_binder_plain_import_dotted_attribute() -> None:
    assert _origin("import a.b", "a.b.User") == "a.b.User"


def test_binder_relative_import_is_absent() -> None:
    assert _origin("from . import C", "C") is None


def test_binder_star_import_is_absent() -> None:
    assert _origin("from a import *", "User") is None


def test_binder_unknown_name_is_absent() -> None:
    assert _origin("import os", "User") is None
