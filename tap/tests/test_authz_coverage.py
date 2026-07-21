"""Unit tests for the authz-coverage scanner (`req-tap-auth-policy-9` Rule A).

Hermetic and Django-free: `scan_authz_coverage` takes source roots, so these drive it
over synthetic source — no app registry, no DB. Rule A flags a call to a privileged
graph sink (`write_batch` / `grift_import` / `_*_internal`) that is NOT reached inside
a gated context — a `@requires_capability` function or an `authorized(...)` block. The
scanner was previously exercised only live through `test_guards.py`; these lock its
gating logic (decorator, `with`-block, nesting, async, and the exemption marker) at the
unit level, the twin of `test_direct_write_coverage.py` for Rule B.
"""

from __future__ import annotations

from pathlib import Path

from tap.authz_coverage import scan_authz_coverage


def _scan(tmp_path: Path, source: str) -> object:
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    return scan_authz_coverage([tmp_path])


def _ungated(result: object) -> set[tuple[str, str]]:
    return {(s.qualname, s.sink) for s in result.ungated_sinks}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Ungated sinks are flagged
# --------------------------------------------------------------------------- #


def test_ungated_sink_is_flagged(tmp_path: Path) -> None:
    result = _scan(tmp_path, "def f():\n    write_batch(x)\n")
    assert _ungated(result) == {("f", "write_batch")}


def test_attribute_style_sink_call_is_flagged(tmp_path: Path) -> None:
    """`svc.write_batch(...)` resolves to the sink name just like the bare call."""
    result = _scan(tmp_path, "def f():\n    svc.write_batch(x)\n")
    assert _ungated(result) == {("f", "write_batch")}


def test_each_sink_name_is_recognized(tmp_path: Path) -> None:
    result = _scan(
        tmp_path, "def f():\n    grift_import(x)\n    _create_node_internal(y)\n    _patch_node_internal(z)\n"
    )
    assert _ungated(result) == {("f", "grift_import"), ("f", "_create_node_internal"), ("f", "_patch_node_internal")}


def test_non_sink_call_is_ignored(tmp_path: Path) -> None:
    result = _scan(tmp_path, "def f():\n    some_other_helper(x)\n")
    assert _ungated(result) == set()


# --------------------------------------------------------------------------- #
# Gated contexts cover the sink
# --------------------------------------------------------------------------- #


def test_requires_capability_decorator_gates(tmp_path: Path) -> None:
    result = _scan(tmp_path, "@requires_capability('grid.write')\ndef f():\n    write_batch(x)\n")
    assert _ungated(result) == set()


def test_authorized_block_gates(tmp_path: Path) -> None:
    result = _scan(tmp_path, "def f():\n    with authorized(cap):\n        write_batch(x)\n")
    assert _ungated(result) == set()


def test_authorized_attribute_block_gates(tmp_path: Path) -> None:
    """`with ctx.authorized(...)` gates as well as the bare-name form."""
    result = _scan(tmp_path, "def f():\n    with ctx.authorized(cap):\n        write_batch(x)\n")
    assert _ungated(result) == set()


def test_nested_function_inside_gated_stays_covered(tmp_path: Path) -> None:
    """The outer gate authorizes the whole synchronous call, incl. a nested def."""
    src = "@requires_capability('c')\ndef outer():\n    def inner():\n        write_batch(x)\n    inner()\n"
    assert _ungated(_scan(tmp_path, src)) == set()


def test_async_decorated_function_gates(tmp_path: Path) -> None:
    result = _scan(tmp_path, "@requires_capability('c')\nasync def f():\n    write_batch(x)\n")
    assert _ungated(result) == set()


def test_async_authorized_block_gates(tmp_path: Path) -> None:
    result = _scan(tmp_path, "async def f():\n    async with authorized(cap):\n        write_batch(x)\n")
    assert _ungated(result) == set()


# --------------------------------------------------------------------------- #
# Gate scope bookkeeping — a gate does not leak to a sibling
# --------------------------------------------------------------------------- #


def test_gate_does_not_leak_to_sibling_function(tmp_path: Path) -> None:
    """Depth pops on leaving the gated function: a later ungated sibling is flagged."""
    src = "@requires_capability('c')\ndef a():\n    write_batch(x)\n\n\ndef b():\n    grift_import(y)\n"
    assert _ungated(_scan(tmp_path, src)) == {("b", "grift_import")}


# --------------------------------------------------------------------------- #
# Exemption marker
# --------------------------------------------------------------------------- #


def test_exemption_marker_skips_the_sink(tmp_path: Path) -> None:
    result = _scan(tmp_path, "def f():\n    write_batch(x)  # TAP-AUTHZ-COV: gated by caller one frame up\n")
    assert _ungated(result) == set()
    assert [(s.qualname, s.sink) for s in result.exempt_skipped] == [("f", "write_batch")]  # type: ignore[attr-defined]
