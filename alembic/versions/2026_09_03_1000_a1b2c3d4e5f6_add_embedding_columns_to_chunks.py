"""add embedding columns to chunks

Revision ID: a1b2c3d4e5f6
Revises: 9e94fbe6ad9b
Create Date: 2026-09-03 10:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9e94fbe6ad9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("embedding_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "embedding_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "embedding_status")
    op.drop_column("chunks", "embedding_id")
