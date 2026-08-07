"""Cursor pagination primitives.

Every list endpoint in the API uses this — not offset/limit — so results
stay stable under concurrent inserts/deletes and so we don't have to
recompute an expensive `OFFSET` scan against large tables in later phases.

The cursor is an opaque, base64-encoded token from the caller's point of
view; internally it just encodes the sort key of the last item seen.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

ItemT = TypeVar("ItemT")


class InvalidCursorError(Exception):
    """Raised when a client-supplied cursor cannot be decoded."""


def encode_cursor(value: str) -> str:
    """Encode a sort-key value into an opaque cursor token."""
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> str:
    """Decode an opaque cursor token back into its sort-key value.

    Raises:
        InvalidCursorError: if `cursor` is not validly encoded.
    """
    try:
        return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise InvalidCursorError("The provided cursor is not valid.") from exc


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Pagination parameters parsed from a request's query string."""

    limit: int
    cursor: str | None = None


class Page(BaseModel, Generic[ItemT]):
    """A single page of results, generic over the item type.

    `next_cursor` is `None` when this is the last page.
    """

    items: list[ItemT]
    has_more: bool = Field(description="Whether another page is available after this one.")
    next_cursor: str | None = Field(
        default=None, description="Pass as the `cursor` query parameter to fetch the next page."
    )
