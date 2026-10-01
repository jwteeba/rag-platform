"""Retrieval domain exceptions."""

from __future__ import annotations

from rag_platform.core.exceptions import NotFoundError, ValidationError


class NoResultsFoundError(NotFoundError):
    message = "No matching chunks found for the given query."
    error_type = "no-results-found"


class InvalidQueryError(ValidationError):
    message = "The search query is invalid."
    error_type = "invalid-query"
