"""TAP Core exceptions."""


class InvalidEdgeError(Exception):
    """Raised when edge creation violates constraints."""

    pass


class EdgePropertyValidationError(Exception):
    """Raised when edge properties fail JSON Schema validation."""

    pass
