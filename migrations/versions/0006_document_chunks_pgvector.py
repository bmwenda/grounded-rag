"""Store document chunks and embeddings in PostgreSQL pgvector.

Revision ID: 0006_document_chunks_pgvector
Revises: 0005_chat_retention_indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "0006_document_chunks_pgvector"
down_revision: str | Sequence[str] | None = "0005_chat_retention_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("index_version", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("embedding", VECTOR(3072), nullable=False),
    )
    op.create_index(
        "ix_document_chunks_document_id", "document_chunks", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
