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


class CollectorNotReadyError(TapCaresError):
    """Raised by the run-task body when phase-1 self-test is not runnable.

    The job has already been terminal-patched FAILED with the self-test
    summary and full `self_test` detail (standard collector failure mode,
    req-tap-cares-collector-failure-mode). This exception is then raised so
    Django Tasks' own failure machinery sees the failure
    (req-tap-cares-collector-failure-mode-5). It carries no secret-bearing
    detail — only the operator-facing self-test summary.
    """

    pass


# ---------------------------------------------------------------------------
# Secrets (spec-tap-cares-secrets.md)
# ---------------------------------------------------------------------------


class SecretError(TapCaresError):
    """Base class for tap_cares secrets subsystem errors."""

    pass


class SecretLoadError(SecretError):
    """Raised at startup when a `*.secret.json` file fails to load.

    Covers malformed JSON, missing required fields, basename/key mismatch,
    and any other structural problem detected during registration.
    """

    pass


class SecretDuplicateError(SecretLoadError):
    """Raised when two secret files declare the same `scope:key`."""

    pass


class SecretNotFoundError(SecretError):
    """Raised at runtime when a capability resolves a SecretRef that is not registered."""

    pass


class SecretValidationError(SecretError):
    """Raised by consumer-side validation when a resolved secret does not match
    the kind or schema the consumer requires."""

    pass


class InvalidSecretRegistryKeyError(SecretError):
    """Raised when a scope or key fails the secret_registry format validator."""

    pass
