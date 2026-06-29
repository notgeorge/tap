"""First-party health-probe registry.

req-tap-health-probe-registry (spec-tap-health-v0.md).

Reuses the flat `tap_grid.registry.Registry` (not `ScopedRegistry`: probe
names are globally unique, which the flat `{name: ...}` report output
requires), wrapped by `register_health_probe(...)` — the same pattern as
`register_search_runner`. Apps self-register their probes from their own
`AppConfig.ready()` by importing the module that calls this; registration only
appends a callable, so it accesses no DB and is `ready()`-safe (the probe body
runs later, at `run_health()` time).

`group` is carried as a field on the stored `HealthProbe` (clustering /
ownership), not as a registry scope, so `name` stays globally unique. `requires`
is the declared least-privilege capability slot — captured now, enforced later
(req-tap-health-probe-actor); v0 probes pass `requires=()`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from tap.registry import Registry
from tap_health.results import ProbeResult


@dataclass(frozen=True)
class HealthProbe:
    """A registered probe: its identity, the callable, and its declared metadata.

    The canonical record — the `register_health_probe` signature, this dataclass,
    and the acceptance criteria all agree on exactly these fields.
    """

    name: str
    probe: Callable[[], ProbeResult]
    group: str = "core"
    critical: bool = False
    requires: tuple[str, ...] = field(default_factory=tuple)


health_probe_registry: Registry[HealthProbe] = Registry(
    "health_probe",
    title="Health Probe Registry",
    description="First-party health probes contributed by apps from their ready().",
)


def register_health_probe(
    name: str,
    probe: Callable[[], ProbeResult],
    *,
    group: str = "core",
    critical: bool = False,
    requires: Sequence[str] = (),
) -> None:
    """Register a named health probe.

    Args:
        name: Globally-unique probe key (the report is keyed by it). A duplicate
            raises `ImproperlyConfigured` at registration (startup).
        probe: Zero-arg callable returning a `ProbeResult`. Run at
            `run_health()` time, not at registration.
        group: Owning namespace for clustering/ownership (default `"core"`).
        critical: Whether an `unhealthy` result flips the overall verdict.
        requires: Declared capabilities (least-privilege slot; not enforced in
            v0). Captured for forward-compatibility (req-tap-health-probe-actor).
    """
    health_probe_registry.register(
        name,
        HealthProbe(name=name, probe=probe, group=group, critical=critical, requires=tuple(requires)),
    )


__all__ = ["HealthProbe", "health_probe_registry", "register_health_probe"]
