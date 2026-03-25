"""TAP Core exceptions."""


class InvalidEdgeError(Exception):
    """Raised when edge creation violates constraints."""

    pass


class EdgePropertyValidationError(Exception):
    """Raised when edge properties fail JSON Schema validation."""

    pass


class InvalidSearchDefinitionError(Exception):
    """Raised when a search definition is structurally invalid at execution time."""

    pass


class SearchRunnerNotFoundError(Exception):
    """Raised when a module runner_key cannot be resolved in the search runner registry."""

    pass


class SearchExecutionError(Exception):
    """Raised on hard failures during search execution (DB error, invalid result envelope, etc.)."""

    pass


class NoBatchContextError(Exception):
    """Raised when a FLIP-enabled model is saved without an active batch context."""

    pass
