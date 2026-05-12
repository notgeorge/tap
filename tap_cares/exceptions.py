"""tap_cares exceptions."""


class TapCaresError(Exception):
    """Base class for tap_cares-specific exceptions."""

    pass


class CollectorNotFoundError(TapCaresError):
    """Raised when a Collector's registry key cannot be resolved in collector_registry."""

    pass


class InvalidCollectorRegistryKeyError(TapCaresError):
    """Raised when a scope or key fails the collector_registry format validator."""

    pass
