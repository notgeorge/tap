"""Boot-profile loading, schema validation, and parsing.

The bootloader owns profile handling (req-boot-app): this module resolves a
profile id to its `boot/<id>.boot.json` file, validates it against the boot-profile
JSON Schema (shape only — semantic pre-resolution of plugin/collector keys
happens in the population phase, req-boot-population-4), and parses it into a
typed `BootProfile`. The richer app-owned multi-section composition is deferred
(req-boot-sections); v0 reads the single `population` section directly.

Spec: specs/spec-tap-boot-v0.md (req-boot-profile).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

from tap.jsonfiles import JsonFileError, discover_json_files, instance_id, load_json_file

# Declared public surface. tap_boot.profile is the boot-profile *contract* (the
# schema types + loaders) that the boot commands and orchestrator consume — a small,
# legitimately-public API. Declared explicitly and frozen by the Family-B public-surface
# ceiling ratchet (tap/guards/public_surface.py); `_parse` and friends stay sealed.
__all__ = [
    "BootProfileError",
    "SeedPluginStep",
    "FireCollectorStep",
    "BootProfile",
    "PopulationStep",
    "DEFAULT_ON_FAILURE",
    "boot_dir",
    "profile_ids",
    "load_profile",
]

_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "boot.schema.json"

# Profile-level default when the population section omits `on_failure`. Abort is
# the safe default: a half-populated standup should fail loud, not look healthy.
DEFAULT_ON_FAILURE = "abort"


class BootProfileError(Exception):
    """Raised when a profile cannot be found, read, or validated."""


@dataclass(frozen=True)
class SeedPluginStep:
    """A `seed-plugin` population step (req-boot-population-2)."""

    plugin: str
    enabled: bool
    bundle: str | None = None
    note: str = ""

    type: str = "seed-plugin"


@dataclass(frozen=True)
class FireCollectorStep:
    """A `fire-collector` population step (req-boot-population-2)."""

    key: str
    enabled: bool
    run_mode: str = "full"
    # Seconds to await this collector's job to a terminal state. None ⇒ the
    # bootloader's default (DEFAULT_COLLECTOR_TIMEOUT_SECONDS). Slow collectors
    # (a full cloud pull) declare a higher value here.
    timeout_seconds: int | None = None
    note: str = ""

    type: str = "fire-collector"


PopulationStep = SeedPluginStep | FireCollectorStep


@dataclass(frozen=True)
class BootProfile:
    profile_id: str
    version: int
    description: str
    on_failure: str
    steps: tuple[PopulationStep, ...]
    # Raw auth section (req-tap-auth-boot). tap_auth owns its schema fragment and
    # validates it strictly in the boot auth phase; the bootloader only carries it.
    auth: dict[str, Any] | None = None

    @property
    def has_population(self) -> bool:
        return bool(self.steps)

    @property
    def has_auth(self) -> bool:
        return bool(self.auth)

    @property
    def enabled_steps(self) -> tuple[PopulationStep, ...]:
        return tuple(s for s in self.steps if s.enabled)


def boot_dir() -> Path:
    """Top-level ``boot/`` directory holding profile data files."""
    return Path(settings.BASE_DIR) / "boot"


def profile_ids() -> list[str]:
    return [instance_id(p, role="boot") for p in discover_json_files(boot_dir(), role="boot")]


def load_profile(profile_id: str) -> BootProfile:
    """Load, schema-validate, and parse ``boot/<profile_id>.boot.json``.

    Raises `BootProfileError` (loud, machine-readable) on a missing file, unreadable
    JSON, or schema-validation failure — never returns a malformed profile.
    """
    path = boot_dir() / f"{profile_id}.boot.json"
    if not path.is_file():
        available = ", ".join(profile_ids()) or "(none)"
        raise BootProfileError(f"Boot profile '{profile_id}' not found at {path}. Available: {available}.")

    try:
        data = load_json_file(path, schema=_SCHEMA_PATH)
    except JsonFileError as exc:
        raise BootProfileError(f"Boot profile '{profile_id}': {exc}") from exc

    return _parse(profile_id, data)


def _parse(profile_id: str, data: dict[str, Any]) -> BootProfile:
    population = data.get("population") or {}
    steps: list[PopulationStep] = []
    for raw in population.get("steps", []):
        if raw["type"] == "seed-plugin":
            steps.append(
                SeedPluginStep(
                    plugin=raw["plugin"],
                    enabled=raw["enabled"],
                    bundle=raw.get("bundle"),
                    note=raw.get("note", ""),
                )
            )
        else:  # schema's oneOf guarantees the only other type is fire-collector
            steps.append(
                FireCollectorStep(
                    key=raw["key"],
                    enabled=raw["enabled"],
                    run_mode=raw.get("run_mode", "full"),
                    timeout_seconds=raw.get("timeout_seconds"),
                    note=raw.get("note", ""),
                )
            )

    return BootProfile(
        profile_id=profile_id,
        version=data["version"],
        description=data.get("description", ""),
        on_failure=population.get("on_failure", DEFAULT_ON_FAILURE),
        steps=tuple(steps),
        auth=data.get("auth"),
    )
