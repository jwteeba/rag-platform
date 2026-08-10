"""UUIDv7 primary key generation.

UUIDv7 embeds a millisecond timestamp in its high bits, so values generated
close together sort close together. That gives a Postgres B-tree primary
key index much better locality than UUIDv4's fully random values — new rows
insert at the end of the index rather than at random pages throughout it,
which matters once a table has real write volume.

Python's stdlib `uuid` module doesn't gain a `uuid7()` function until 3.14;
this project targets 3.12, hence the small `uuid6` dependency instead of a
hand-rolled implementation of an IETF-standardized algorithm.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from uuid6 import uuid7

if TYPE_CHECKING:
    import uuid


def generate_uuid7() -> uuid.UUID:
    """Generate a new, time-ordered UUIDv7."""
    return uuid7()
