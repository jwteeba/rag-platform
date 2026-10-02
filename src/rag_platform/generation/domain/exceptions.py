"""Generation domain exceptions."""

from __future__ import annotations

from rag_platform.core.exceptions import NotFoundError, ValidationError


class TemplateNotFoundError(NotFoundError):
    message = "Prompt template not found."
    error_type = "template-not-found"


class TemplateRenderError(ValidationError):
    message = "Failed to render the prompt template."
    error_type = "template-render-error"


class ContextWindowExceededError(ValidationError):
    message = "The assembled context exceeds the maximum context window."
    error_type = "context-window-exceeded"
