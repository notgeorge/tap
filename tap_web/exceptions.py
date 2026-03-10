"""TAP Web validation exceptions."""


class PageSlugValidationError(ValueError):
    """Raised when a Page slug fails normalization or security rules."""


class PageLayoutValidationError(ValueError):
    """Raised when a Page layout fails JSON Schema validation."""


class PanelStaticAssetValidationError(ValueError):
    """Raised when a Panel asset path references an external URL."""
