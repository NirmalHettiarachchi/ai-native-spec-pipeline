"""Domain errors surfaced by the pipeline CLI."""


class PipelineError(Exception):
    """Base exception for user-correctable pipeline failures."""


class SpecValidationError(PipelineError):
    """Raised when a feature specification cannot be parsed or validated."""

