"""added duplicate check for document upload

Revision ID: c956e35ded12
Revises: a1b2c3d4e5f6
Create Date: 2026-09-15 20:25:25.969201
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c956e35ded12"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.alter_column(
        "documents",
        "content_hash",
        nullable=False,
    )

    op.create_unique_constraint(
        "uq_documents_owner_content_hash",
        "documents",
        ["owner_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_owner_content_hash",
        "documents",
        type_="unique",
    )

    op.drop_column("documents", "content_hash")
