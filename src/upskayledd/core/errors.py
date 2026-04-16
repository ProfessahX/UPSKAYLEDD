class UpskayleddError(Exception):
    """Base error for the project."""


class ConfigError(UpskayleddError):
    """Raised when config files are missing or invalid."""


class CompatibilityError(UpskayleddError):
    """Raised when persisted artifacts are incompatible."""


class ExternalToolError(UpskayleddError):
    """Raised when an external tool invocation fails."""

