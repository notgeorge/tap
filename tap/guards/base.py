"""Base classes for TAP's development-time guards.

A *guard* is a build/CI-time check that asserts a structural invariant about the
source tree — every test file is collected, no secret-shaped file exists, every
privileged sink is gated, a ratcheting baseline hasn't regressed. Guards have **no
runtime consumer**: a booted TAP instance never queries them, so — unlike
collectors or node-types — they are deliberately NOT in a runtime registry and do
not register in `AppConfig.ready()`. Their only "registry" is subclass enumeration
evaluated at test time (`all_guards()`), which vanishes when the test process exits.

The base earns its place for two reasons, not persistence:

1. **Findability.** `all_guards()` enumerates every `Guard`, so a meta-test can run
   them uniformly *and* assert each corresponds to a row in the Validation Map — the
   mechanical close on the "a guard emerged without being accounted for" failure
   (`spec-dev-validation.md` `req-dev-validation-map`).
2. **Shared ratchet mechanics.** `CeilingRatchet` wraps the compare-and-report in
   `tap.ratchet` for the per-commit set-based ratchets, so a subclass writes only
   its bespoke `measure()`. The floor direction (`tap.ratchet.ratchet_floor`) has
   only a script-invoked consumer today (the ~10-15 min Gryphon branch-coverage
   run, which cannot measure in-process), so it stays a bare function the script
   calls — no `FloorRatchet` Guard subclass until a per-commit floor exists.

A concrete guard declares a non-empty ``slug`` (its stable id) and ``map_row`` (the
Validation Map surface name it corresponds to) and implements ``check()``. Base
classes leave ``slug`` empty and are not enumerated.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import ClassVar

from tap.ratchet import ratchet_ceiling, read_baseline_set

# tap/guards/base.py → parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_SPEC = REPO_ROOT / "specs" / "spec-dev-validation.md"

# Every concrete Guard subclass, in definition order. Populated at import time
# (see tap/guards/__init__.py, which imports the guard modules); consumed only by
# tests. Not a runtime registry.
_GUARDS: list[type[Guard]] = []


class Guard(abc.ABC):
    """A development-time structural check. Subclasses implement `check()`."""

    #: Stable id (also the pytest parametrize id). Concrete guards MUST set it.
    slug: ClassVar[str] = ""
    #: The Validation Map surface name this guard corresponds to (co-change discipline).
    map_row: ClassVar[str] = ""
    #: Why this guard exists — the failure it prevents, in the author's words. Required
    #: (enforced by the meta-test): a guard that cannot say why it is here is dead weight.
    #: A first-class field, not just a docstring, so the whole guard set is self-describing.
    description: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Only concrete guards declare a slug in their own body; base classes
        # (Ratchet, CeilingRatchet, …) leave it empty and are not enumerated.
        if cls.__dict__.get("slug"):
            _GUARDS.append(cls)

    @abc.abstractmethod
    def check(self) -> None:
        """Assert the invariant; raise AssertionError (or a subclass) on violation."""


class CeilingRatchet(Guard):
    """A ceiling-to-zero ratchet: `measure()` must not grow past the baseline set."""

    #: Committed baseline file (line-per-entry; blanks/`#`-comments ignored).
    baseline_path: ClassVar[Path]
    #: Surface-specific guidance shown when a NEW item appears (the right fix first).
    new_hint: ClassVar[str] = ""

    @abc.abstractmethod
    def measure(self) -> set[str]:
        """Return the freshly measured set of flagged items (bespoke per surface)."""

    def check(self) -> None:
        ratchet_ceiling(
            current=self.measure(),
            baseline=read_baseline_set(self.baseline_path),
            surface=self.map_row,
            baseline_path=self.baseline_path,
            new_hint=self.new_hint,
        )


def all_guards() -> list[Guard]:
    """Every registered concrete guard, instantiated. Import-time cheap; `check()` does the work."""
    return [cls() for cls in _GUARDS]


def validation_map_surfaces() -> set[str]:
    """The set of surface names (first column) in the Validation Map table.

    Parses the Markdown table under `#### The Map` in spec-dev-validation.md up to
    the trailing "Rows marked" note. Used by the completeness meta-test to assert
    every guard's `map_row` is accounted for — so a guard cannot ship unmapped.
    """
    text = _VALIDATION_SPEC.read_text(encoding="utf-8")
    lines = text.splitlines()
    surfaces: set[str] = set()
    in_map = False
    for line in lines:
        if line.startswith("#### The Map"):
            in_map = True
            continue
        if in_map:
            if line.startswith("Rows marked") or line.startswith("#"):
                break
            if not line.startswith("|"):
                continue
            first = line.split("|")[1].strip()
            if not first or first == "Surface" or set(first) <= {"-", " ", ":"}:
                continue  # header / separator / empty
            surfaces.add(first)
    return surfaces
