# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.

"""Shared errors for the orchestrator prototype."""


class OrchestratorError(Exception):
    """Base error for orchestrator failures."""


class ConfigurationError(OrchestratorError):
    """Raised when local tool configuration is incomplete."""


class ToolExecutionError(OrchestratorError):
    """Raised when a runtime-facing tool command fails."""


class ContractValidationError(OrchestratorError):
    """Raised when a tool returns malformed runtime contract JSON."""


class InstallationError(OrchestratorError):
    """Raised when sibling tool bootstrap/install setup fails."""
