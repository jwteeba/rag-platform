"""Unit tests for `rag_platform.core.errors` and the exception hierarchy."""

from __future__ import annotations

from http import HTTPStatus

from rag_platform.core.errors import build_problem_detail, status_for_error
from rag_platform.core.exceptions import (
    ApplicationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)


class CustomNotFoundError(NotFoundError):
    """A hypothetical domain-specific subclass, e.g. from a future phase."""

    error_type = "document-not-found"


class TestStatusForError:
    def test_not_found_error_maps_to_404(self) -> None:
        assert status_for_error(NotFoundError()) is HTTPStatus.NOT_FOUND

    def test_validation_error_maps_to_422(self) -> None:
        assert status_for_error(ValidationError()) is HTTPStatus.UNPROCESSABLE_ENTITY

    def test_conflict_error_maps_to_409(self) -> None:
        assert status_for_error(ConflictError()) is HTTPStatus.CONFLICT

    def test_unmapped_application_error_maps_to_500(self) -> None:
        assert status_for_error(ApplicationError()) is HTTPStatus.INTERNAL_SERVER_ERROR

    def test_subclass_of_mapped_error_resolves_via_mro(self) -> None:
        assert status_for_error(CustomNotFoundError()) is HTTPStatus.NOT_FOUND


class TestBuildProblemDetail:
    def test_builds_expected_shape(self) -> None:
        problem = build_problem_detail(
            error_type="not-found",
            status=HTTPStatus.NOT_FOUND,
            detail="Document xyz was not found.",
            instance="/api/v1/documents/xyz",
            request_id="req-123",
        )

        assert problem.type == "https://errors.rag-platform.dev/not-found"
        assert problem.title == "Not Found"
        assert problem.status == 404
        assert problem.detail == "Document xyz was not found."
        assert problem.instance == "/api/v1/documents/xyz"
        assert problem.request_id == "req-123"

    def test_request_id_defaults_to_none(self) -> None:
        problem = build_problem_detail(
            error_type="validation-error",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Invalid input.",
            instance="/api/v1/things",
        )

        assert problem.request_id is None
