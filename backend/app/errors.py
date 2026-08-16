"""Typed errors mapped to the CLI exit codes in contracts/cli-contract.md."""

from __future__ import annotations


class PipelineError(Exception):
    """Base for all pipeline failures. `exit_code` drives the CLI's return status."""

    exit_code: int = 1


class UnregisteredSourceError(PipelineError):
    """A PDF in the corpus has no data/sources.yaml entry (FR-002)."""

    exit_code = 1


class NoTextLayerError(PipelineError):
    """PDF has no extractable text — likely scanned. OCR is out of scope."""

    exit_code = 2


class NoSectionsError(PipelineError):
    """No section hierarchy detected, so chunks could not be attributed."""

    exit_code = 3


class EmbeddingProviderError(PipelineError):
    """Embedding provider failed after retries."""

    exit_code = 4


class ConfigurationError(PipelineError):
    """Missing API key, bad paths, or contradictory settings."""

    exit_code = 5
