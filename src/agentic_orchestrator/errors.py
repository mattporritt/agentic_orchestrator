"""Shared errors for the orchestrator prototype."""


class OrchestratorError(Exception):
    """Base error for orchestrator failures."""


class ConfigurationError(OrchestratorError):
    """Raised when local tool configuration is incomplete."""


class ToolExecutionError(OrchestratorError):
    """Raised when a runtime-facing tool command fails."""


class ContractValidationError(OrchestratorError):
    """Raised when a tool returns malformed runtime contract JSON."""
