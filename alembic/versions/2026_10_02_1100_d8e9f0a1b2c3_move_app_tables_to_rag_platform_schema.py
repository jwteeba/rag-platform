"""move application tables into rag_platform schema

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-02 11:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "users",
    "refresh_tokens",
    "documents",
    "chunks",
    "prompt_templates",
    "conversations",
    "messages",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS rag_platform")
    op.execute(
        """
        DO $$
        DECLARE table_name text;
        BEGIN
            FOREACH table_name IN ARRAY ARRAY[
                'users', 'refresh_tokens', 'documents', 'chunks',
                'prompt_templates', 'conversations', 'messages'
            ] LOOP
                IF to_regclass(format('%I.%I', 'public', table_name)) IS NOT NULL THEN
                    IF to_regclass(format('%I.%I', 'rag_platform', table_name)) IS NOT NULL THEN
                        RAISE EXCEPTION
                            'Duplicate table exists in public and rag_platform: %', table_name;
                    END IF;
                    EXECUTE format(
                        'ALTER TABLE public.%I SET SCHEMA rag_platform', table_name
                    );
                END IF;
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    for table_name in reversed(_TABLES):
        op.execute(f'ALTER TABLE IF EXISTS rag_platform."{table_name}" SET SCHEMA public')
