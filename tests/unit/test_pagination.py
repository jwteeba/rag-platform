"""Unit tests for `rag_platform.core.pagination`."""

from __future__ import annotations

import pytest

from rag_platform.core.pagination import InvalidCursorError, decode_cursor, encode_cursor


class TestCursorRoundTrip:
    def test_encode_then_decode_returns_original_value(self) -> None:
        original = "some-sort-key-value"

        cursor = encode_cursor(original)

        assert decode_cursor(cursor) == original

    def test_cursor_is_opaque_base64_not_the_raw_value(self) -> None:
        cursor = encode_cursor("secret-id-123")

        assert cursor != "secret-id-123"

    def test_decode_rejects_garbage_cursor(self) -> None:
        with pytest.raises(InvalidCursorError):
            decode_cursor("not valid base64!!! 🎉")
