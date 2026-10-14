"""Index soft-deletion timestamps for retention scans.

Revision ID: 0005_chat_retention_indexes
Revises: 0004_chat_generation_claim
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_chat_retention_indexes"
down_revision: str | Sequence[str] | None = "0004_chat_generation_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_index("ix_chats_deleted_at", "chats", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_chats_deleted_at", table_name="chats")
    op.drop_index("ix_users_deleted_at", table_name="users")
