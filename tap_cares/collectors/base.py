"""CollectorBase — abstract base class for tap_cares collector implementations.

req-tap-cares-collector-module-class (spec-tap-cares-collector.md).

Concrete collector classes register with `collector_registry` via
`tap_cares.registry.register_collector`. The runtime resolves the registered
class, builds a CollectorConfig, instantiates with that config, and calls
run().
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from tap_cares.collectors.config import CollectorConfig


class CollectorBase(ABC):
    def __init__(self, config: CollectorConfig) -> None:
        self.config = config

    @abstractmethod
    def run(self) -> None:
        """Execute one collection.

        v0 receives no direct arguments — per-run data flows through self.config.
        Implementations may submit results through the approved GRIFT import
        surface but must not mutate grid state through other paths.
        """
        ...
