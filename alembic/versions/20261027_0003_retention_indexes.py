"""Index the timestamps the retention job deletes by."""

from alembic import op


revision = "20261027_0003"
down_revision = "20261026_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])
    op.create_index("ix_task_records_created_at", "task_records", ["created_at"])
    op.create_index("ix_answer_cache_entries_updated_at", "answer_cache_entries", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_answer_cache_entries_updated_at", table_name="answer_cache_entries")
    op.drop_index("ix_task_records_created_at", table_name="task_records")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
